import XCTest

extension XCUIApplication {
    /// Counts red-ish and brand-green pixels inside a frame of the current screen, to check an action's colour.
    func colorCounts(in frame: CGRect) -> (red: Int, green: Int) {
        guard let cg = screenshot().image.cgImage else { return (0, 0) }
        let scale = CGFloat(cg.width) / self.frame.width
        var red = 0, green = 0
        for x in stride(from: Int(frame.minX * scale), to: Int(frame.maxX * scale), by: 3) {
            for y in stride(from: Int(frame.minY * scale), to: Int(frame.maxY * scale), by: 3) {
                guard x >= 0, y >= 0, x < cg.width, y < cg.height,
                      let crop = cg.cropping(to: CGRect(x: x, y: y, width: 1, height: 1)) else { continue }
                var px = [UInt8](repeating: 0, count: 4)
                let context = CGContext(data: &px, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
                                        space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
                context?.draw(crop, in: CGRect(x: 0, y: 0, width: 1, height: 1))
                let r = Int(px[0]), g = Int(px[1]), b = Int(px[2])
                if r > 170, g < 110, b < 110 { red += 1 }
                if g > r + 20, g > b, r < 90 { green += 1 }
            }
        }
        return (red, green)
    }
}
