import XCTest

final class AuthFlowUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-uiTesting"]
        app.launch()
    }

    func testFreshLaunchShowsServerSetup() {
        XCTAssertTrue(app.staticTexts["Connect to your Rapport server"].waitForExistence(timeout: 5))
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
