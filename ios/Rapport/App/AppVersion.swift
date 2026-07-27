import Foundation

/// Reads the app's marketing version + build number from the bundle so
/// there's a single place to check "which build is this" — previously
/// Info.plist hardcoded literal "1.0"/"1" instead of the MARKETING_VERSION/
/// CURRENT_PROJECT_VERSION build settings, so no rebuild ever actually
/// changed what was visible, and there was no in-app way to tell builds
/// apart at all.
enum AppVersion {
    static var shortVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
    }

    static var buildNumber: String {
        Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
    }

    static var displayString: String {
        "Rapport \(shortVersion) (\(buildNumber))"
    }
}
