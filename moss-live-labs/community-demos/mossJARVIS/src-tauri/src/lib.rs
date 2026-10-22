use std::{env, fs, net::TcpStream, path::Path, process::{Child, Command, Stdio}, sync::Mutex, thread, time::{Duration, Instant}};
use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

struct ServerProcess(Mutex<Option<Child>>);

fn packaged_node_path(server_dir: &Path) -> Result<std::ffi::OsString, Box<dyn std::error::Error>> {
    let node_modules = server_dir.join("node_modules");
    let mut paths = vec![node_modules.clone()];
    let pnpm_store = node_modules.join(".pnpm");
    if pnpm_store.is_dir() {
        for entry in fs::read_dir(pnpm_store)? {
            let package_modules = entry?.path().join("node_modules");
            if package_modules.is_dir() {
                paths.push(package_modules);
            }
        }
    }
    Ok(env::join_paths(paths)?)
}

fn launch_server(app: &tauri::AppHandle) -> Result<Child, Box<dyn std::error::Error>> {
    let server_dir = app.path().resource_dir()?.join("server");
    let node_binary = app.path().resource_dir()?.join("runtime").join("node");
    let data_dir = app.path().app_data_dir()?;
    let node_path = packaged_node_path(&server_dir)?;
    fs::create_dir_all(&data_dir)?;
    let child = Command::new(node_binary)
        .arg("server.js")
        .current_dir(server_dir)
        .env("PORT", "3000")
        .env("HOSTNAME", "127.0.0.1")
        .env("JARVIS_DATA_DIR", data_dir)
        .env("NODE_PATH", node_path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()?;
    Ok(child)
}

fn wait_for_server() -> Result<(), Box<dyn std::error::Error>> {
    let deadline = Instant::now() + Duration::from_secs(15);
    while Instant::now() < deadline {
        if TcpStream::connect("127.0.0.1:3000").is_ok() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(150));
    }
    Err("Jarvis local server did not start within 15 seconds".into())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .manage(ServerProcess(Mutex::new(None)))
        .setup(|app| {
            #[cfg(not(debug_assertions))]
            {
                let child = launch_server(app.handle())?;
                *app.state::<ServerProcess>().0.lock().unwrap() = Some(child);
                wait_for_server()?;
            }

            WebviewWindowBuilder::new(
                app,
                "main",
                WebviewUrl::External("http://127.0.0.1:3000".parse().unwrap()),
            )
            .title("J.A.R.V.I.S.")
            .inner_size(1180.0, 760.0)
            .min_inner_size(900.0, 620.0)
            .decorations(false)
            .transparent(true)
            .always_on_top(true)
            .resizable(true)
            .shadow(false)
            .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build Jarvis");

    app.run(|app, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            if let Some(mut child) = app.state::<ServerProcess>().0.lock().unwrap().take() {
                let _ = child.kill();
            }
        }
    });
}
