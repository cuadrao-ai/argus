/// The model tests run on the Mac; the app's ScanTrace writes to Documents in Debug, so the tests use this no-op.
enum ScanTrace {
    static func mark(_ step: String) {}
}
