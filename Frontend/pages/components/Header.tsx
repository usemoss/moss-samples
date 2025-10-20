import React from "react";
import config from "../index.json";
import ThemeToggle from "./ThemeToggle";

const Header = () => {
  const navigation = config.navigation;
  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-white/80 dark:bg-zinc-950/90 backdrop-blur-md border-b border-gray-200 dark:border-zinc-800 transition-colors duration-300">
      <nav className="px-8 lg:px-32 py-4">
        <ul className="flex gap-x-8 items-center justify-center lg:justify-end">
          {navigation.map((item) => (
            <li key={item.title}>
              <a 
                href={`#${item.title}`}
                className="text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-fuchsia-600 dark:hover:text-fuchsia-400 transition-colors duration-200"
              >
                {item.title}
              </a>
            </li>
          ))}
          <li>
            <ThemeToggle />
          </li>
        </ul>
      </nav>
    </header>
  );
};

export default Header;