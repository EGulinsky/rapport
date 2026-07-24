import Testing
@testable import Rapport
import Foundation

struct APIErrorTests {
    @Test func decodesStringDetail() {
        let json = #"{"detail": "Not found"}"#
        let error = APIError.from(data: Data(json.utf8), statusCode: 404)
        #expect(error.message == "Not found")
        #expect(error.errorKey == nil)
        #expect(error.statusCode == 404)
    }

    @Test func decodesErrorKeyObjectDetail() {
        // Matches backend/app/error_keys.py's api_error() shape exactly.
        let json = #"{"detail": {"error_key": "auth.login_failed", "message": "E-Mail oder Passwort ist falsch."}}"#
        let error = APIError.from(data: Data(json.utf8), statusCode: 401)
        #expect(error.errorKey == "auth.login_failed")
        #expect(error.message == "E-Mail oder Passwort ist falsch.")
    }

    @Test func fallsBackToRawBodyForUnexpectedShape() {
        let json = "Internal Server Error"
        let error = APIError.from(data: Data(json.utf8), statusCode: 500)
        #expect(error.message == "Internal Server Error")
        #expect(error.errorKey == nil)
    }

    @Test func fallsBackToStatusCodeForEmptyBody() {
        let error = APIError.from(data: Data(), statusCode: 502)
        #expect(error.message == "502")
    }
}
