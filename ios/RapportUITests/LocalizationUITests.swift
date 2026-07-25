import XCTest

/// Verifies the German String Catalog translations actually take effect at
/// runtime — a resource-file typo or a missing "de" localization wouldn't be
/// caught by a build-succeeds check alone.
///
/// `-AppleLanguages`/`-AppleLocale` launch arguments are a known Simulator
/// quirk: they don't stay scoped to the one launched process, they get
/// written as the Simulator's *global* language preference and persist
/// across every subsequent app launch on that device — including other test
/// classes' runs in the same `xcodebuild test` invocation — until something
/// else overrides it. Verified directly against the booted Simulator's
/// `.GlobalPreferences` after a run: it stayed on German and broke
/// `AuthFlowUITests`' English-text assertions afterward. `Process`/`simctl`
/// isn't usable here to reset it — it's unavailable on the iOS SDK this
/// test target compiles against, even though the test runner itself
/// executes on the Mac. So instead of resetting state from this side,
/// `AuthFlowUITests` pins English explicitly via the same launch-argument
/// mechanism, making every locale-sensitive test self-contained regardless
/// of run order.
final class LocalizationUITests: XCTestCase {
    func testServerSetupScreenShowsGermanWhenDeviceLanguageIsGerman() {
        let app = XCUIApplication()
        app.launchArguments = ["-uiTesting", "-AppleLanguages", "(de)", "-AppleLocale", "de_DE"]
        app.launch()

        XCTAssertTrue(app.staticTexts["Mit deinem Rapport-Server verbinden"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Weiter"].exists)
    }
}
