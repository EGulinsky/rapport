import XCTest

/// Covers the sections ApplicationsFlowUITests doesn't: Contacts, Companies,
/// Calendar, Analytics, Review, Audit Log, and Settings navigation. Each
/// test drives the same sidebar -> content navigation established in
/// ApplicationsFlowUITests (targeting "sidebar.<section>" accessibility
/// identifiers rather than visible text, for the same reason documented
/// there: visible section titles can collide with other on-screen text at
/// specific coordinates in the collapsed iPad layout).
final class SidebarNavigationUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["-uiTesting", "-uiTestingMockAPI", "-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
    }

    /// A single "Show Sidebar" tap doesn't reliably land on the sidebar
    /// column — depending on exactly when the collapsed NavigationSplitView
    /// finishes settling after launch, one tap can step back to the content
    /// column instead (verified via app.debugDescription: one run showed
    /// the Applications content list, not the MainSection sidebar list,
    /// after a single tap). Retrying the tap until the target row actually
    /// appears is more robust than assuming a fixed number of taps.
    private func navigateToSidebarSection(_ identifier: String) {
        let row = app.descendants(matching: .any)["sidebar.\(identifier)"].firstMatch
        for _ in 0..<4 {
            if row.waitForExistence(timeout: 2) {
                row.tap()
                return
            }
            let showSidebar = app.buttons["Show Sidebar"]
            if showSidebar.waitForExistence(timeout: 2) {
                showSidebar.tap()
            }
        }
        XCTAssertTrue(row.waitForExistence(timeout: 2), "sidebar.\(identifier) never appeared")
        row.tap()
    }

    func testContactsListShowsMockedContact() {
        navigateToSidebarSection("contacts")
        XCTAssertTrue(app.staticTexts["Ada Lovelace"].waitForExistence(timeout: 5))
    }

    func testCompaniesListShowsMockedCompany() {
        navigateToSidebarSection("companies")
        XCTAssertTrue(app.staticTexts["Contoso"].waitForExistence(timeout: 5))
    }

    func testCalendarShowsEmptyStateWhenNoEvents() {
        navigateToSidebarSection("calendar")
        XCTAssertTrue(app.staticTexts["No upcoming events"].waitForExistence(timeout: 5))
    }

    func testAnalyticsShowsPipelineFunnelSection() {
        navigateToSidebarSection("analytics")
        XCTAssertTrue(app.staticTexts["Pipeline funnel"].waitForExistence(timeout: 5))
    }

    func testReviewShowsMockedPendingMatch() {
        navigateToSidebarSection("review")
        XCTAssertTrue(app.staticTexts["Interview invite"].waitForExistence(timeout: 5))
    }

    func testAuditLogShowsMockedEntry() {
        navigateToSidebarSection("auditLog")
        XCTAssertTrue(app.staticTexts["Contoso"].waitForExistence(timeout: 5))
    }

    func testSettingsNavigatesToAccountPanel() {
        navigateToSidebarSection("settings")

        // Same view-transition-timing quirk as navigateToSidebarSection: a
        // single tap on the just-revealed content column's row doesn't
        // always register a push into the detail column, depending on
        // exactly when NavigationSplitView finishes settling from the
        // previous navigation. Retrying the tap is more robust than
        // asserting after one attempt.
        let account = app.staticTexts["Account"].firstMatch
        let profile = app.staticTexts["Profile"]
        for _ in 0..<4 {
            if profile.waitForExistence(timeout: 2) { break }
            if account.waitForExistence(timeout: 2) {
                account.tap()
            }
        }
        XCTAssertTrue(profile.waitForExistence(timeout: 2))
    }
}
