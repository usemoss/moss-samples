require 'json'

package = JSON.parse(File.read(File.join(__dir__, '..', 'package.json')))

# Fetch Moss.xcframework now, while this podspec is being evaluated.
#
# It cannot be done from `prepare_command`: Expo/RN autolinking installs this
# pod from node_modules as a *development* pod (`:path => ...`), and CocoaPods
# only runs `prepare_command` for pods it downloads into `Pods/` — development
# pods skip it entirely. The npm tarball also excludes `ios/Frameworks/` (see
# .npmignore) to keep the package small, so nothing would have created the
# directory that `vendored_frameworks` points at.
#
# Podspec evaluation happens before CocoaPods resolves `vendored_frameworks`,
# which makes this the earliest hook that runs on every install path. The
# script is a no-op once the framework is present, so repeat `pod install`s
# do not re-download.
download_script = File.join(__dir__, 'scripts', 'download-moss-xcframework.sh')
unless system('bash', download_script)
  raise <<~MSG
    [MossReactNative] Could not fetch Moss.xcframework.

    Tried: bash #{download_script}

    This needs network access on the first `pod install`. To use a locally
    built binary instead, place it at #{File.join(__dir__, 'Frameworks', 'Moss.xcframework')}
    and re-run `pod install` — the script skips the download when it exists.
  MSG
end

Pod::Spec.new do |s|
  s.name           = 'MossReactNative'
  s.version        = package['version']
  s.summary        = package['description']
  s.description    = package['description']
  s.license        = package['license']
  s.author         = package['author']
  s.homepage       = package['homepage']
  s.platforms      = { :ios => '16.4' }
  s.swift_version  = '5.9'
  s.source         = { git: 'https://github.com/usemoss/moss.git' }
  s.static_framework = true

  s.dependency 'ExpoModulesCore'

  # System frameworks used by libmoss (see examples/c + Swift SDK)
  s.frameworks = 'Security', 'SystemConfiguration', 'UIKit'

  # NB: no `prepare_command` — see the download block above for why it cannot
  # be relied on here. By this point Frameworks/Moss.xcframework exists.
  s.vendored_frameworks = 'Frameworks/Moss.xcframework'
  s.preserve_paths = [
    'Frameworks/Moss.xcframework',
    'scripts',
  ]

  # Keep Frameworks/ out of the source glob (Expo third-party library guidance)
  s.source_files = '*.{h,m,mm,swift}'

  xc_headers = '"${PODS_XCFRAMEWORKS_BUILD_DIR}/MossReactNative/Headers"'
  xc_libdir  = '"${PODS_XCFRAMEWORKS_BUILD_DIR}/MossReactNative"'

  s.pod_target_xcconfig = {
    'DEFINES_MODULE' => 'YES',
    'OTHER_SWIFT_FLAGS' => '$(inherited) -D EXPO_CONFIGURATION_$(CONFIGURATION:upper)',
    # Make `import MossC` resolve the Headers/module.modulemap from the xcframework
    'HEADER_SEARCH_PATHS' => "$(inherited) #{xc_headers}",
    'SWIFT_INCLUDE_PATHS' => "$(inherited) #{xc_headers}",
    'LIBRARY_SEARCH_PATHS' => "$(inherited) #{xc_libdir}",
    # Simulator binary is arm64-only (Apple Silicon)
    'EXCLUDED_ARCHS[sdk=iphonesimulator*]' => 'x86_64',
  }

  s.user_target_xcconfig = {
    'EXCLUDED_ARCHS[sdk=iphonesimulator*]' => 'x86_64',
  }
end
