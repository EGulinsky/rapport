import XCTest

final class AuthFlowUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        // Pins English explicitly rather than relying on whatever the
        // Simulator's ambient language happens to be — LocalizationUITests
        // sets the Simulator's *global* language when it runs (a known
        // Simulator/XCTest quirk with -AppleLanguages), which would
        // otherwise leak into these English-text assertions depending on
        // test run order.
        app.launchArguments = ["-uiTesting", "-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
    }

    func testFreshLaunchShowsServerSetup() {
        XCTAssertTrue(app.staticTexts["Connect to your server"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.textFields["serverAddressField"].exists)
        XCTAssertFalse(app.buttons["serverContinueButton"].isEnabled)
    }

    func testEnteringServerAddressNavigatesToLogin() {
        let field = app.textFields["serverAddressField"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText("192.168.1.50:8000")

        app.buttons["serverContinueButton"].tap()

        XCTAssertTrue(app.textFields["loginEmailField"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.secureTextFields["loginPasswordField"].exists)
    }

    func testCreateAccountLinkSwitchesToRegisterForm() throws {
        let field = app.textFields["serverAddressField"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText("192.168.1.50:8000")
        app.buttons["serverContinueButton"].tap()

        XCTAssertTrue(app.buttons["goToRegisterButton"].waitForExistence(timeout: 5))
        app.buttons["goToRegisterButton"].tap()

        XCTAssertTrue(app.navigationBars["Create account"].waitForExistence(timeout: 5))
    }
}
