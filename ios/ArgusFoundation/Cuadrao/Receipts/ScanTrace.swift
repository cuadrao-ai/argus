import Foundation

/// Debug and founder-phone builds only: a timestamped line per scan step in Documents/scan-trace.txt,
/// so a freeze on the phone can be read back with devicectl instead of guessed. Release builds compile it away.
enum ScanTrace {
    static func mark(_ step: String) {
        #if DEBUG
        let line = ISO8601DateFormatter.string(from: Date(), timeZone: .current,
                                               formatOptions: [.withInternetDateTime, .withFractionalSeconds])
            + " main=\(Thread.isMainThread) " + step + "\n"
        guard let folder = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        let file = folder.appendingPathComponent("scan-trace.txt")
        if let handle = try? FileHandle(forWritingTo: file) {
            handle.seekToEndOfFile(); handle.write(Data(line.utf8)); try? handle.close()
        } else {
            try? Data(line.utf8).write(to: file)
        }
        #endif
    }
}
