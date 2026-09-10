#!/usr/bin/env swift
//
//  contactsheet.swift
//  Tile many screenshots into a few labelled contact sheets.
//
//  Reading N screenshots one at a time is the expensive part of a visual review.
//  One sheet of 12 costs a single image read, so a 40-screen sweep becomes 4
//  reads instead of 40.
//
//  Usage: swift contactsheet.swift --out DIR [--cols 4] [--rows 3] [--width 420] shot.png ...
//

import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import CoreText

struct Args {
    var out = "."
    var cols = 4
    var rows = 3
    var tileWidth: CGFloat = 420
    var files: [String] = []
}

func parseArgs() -> Args {
    var a = Args()
    var i = 1
    let argv = CommandLine.arguments
    while i < argv.count {
        switch argv[i] {
        case "--out":   a.out = argv[i + 1]; i += 2
        case "--cols":  a.cols = Int(argv[i + 1]) ?? 4; i += 2
        case "--rows":  a.rows = Int(argv[i + 1]) ?? 3; i += 2
        case "--width": a.tileWidth = CGFloat(Double(argv[i + 1]) ?? 420); i += 2
        default:        a.files.append(argv[i]); i += 1
        }
    }
    return a
}

let args = parseArgs()
guard !args.files.isEmpty else {
    FileHandle.standardError.write("contactsheet: no input images\n".data(using: .utf8)!)
    exit(2)
}

let labelHeight: CGFloat = 34
let pad: CGFloat = 12
let space = CGSize(width: pad, height: pad)

func loadImage(_ path: String) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}

func label(for path: String) -> String {
    (path as NSString).lastPathComponent
        .replacingOccurrences(of: ".png", with: "")
}

/// Draw text centred in a bar, truncating with an ellipsis when it overflows.
func draw(_ text: String, in ctx: CGContext, rect: CGRect, size: CGFloat) {
    let font = CTFontCreateWithName("Menlo" as CFString, size, nil)
    let attrs: CFDictionary = [
        kCTFontAttributeName: font,
        kCTForegroundColorAttributeName: CGColor(red: 0.95, green: 0.95, blue: 0.95, alpha: 1),
    ] as CFDictionary

    func line(_ s: String) -> CTLine {
        CTLineCreateWithAttributedString(CFAttributedStringCreate(nil, s as CFString, attrs)!)
    }

    var shown = text
    var ctLine = line(shown)
    while CTLineGetTypographicBounds(ctLine, nil, nil, nil) > Double(rect.width - 8), shown.count > 4 {
        shown = String(shown.dropLast(2)) + "\u{2026}"
        shown = shown.replacingOccurrences(of: "\u{2026}\u{2026}", with: "\u{2026}")
        ctLine = line(shown)
    }
    let w = CTLineGetTypographicBounds(ctLine, nil, nil, nil)
    ctx.textPosition = CGPoint(x: rect.midX - CGFloat(w) / 2, y: rect.minY + size * 0.55)
    CTLineDraw(ctLine, ctx)
}

let perSheet = args.cols * args.rows
let sheets = stride(from: 0, to: args.files.count, by: perSheet).map {
    Array(args.files[$0 ..< min($0 + perSheet, args.files.count)])
}

var written: [String] = []

for (index, group) in sheets.enumerated() {
    let images = group.compactMap { path -> (String, CGImage)? in
        guard let img = loadImage(path) else { return nil }
        return (label(for: path), img)
    }
    guard !images.isEmpty else { continue }

    // Tile height comes from the tallest aspect ratio so nothing is cropped.
    let maxRatio = images.map { CGFloat($0.1.height) / CGFloat($0.1.width) }.max() ?? 2
    let tileH = (args.tileWidth * maxRatio).rounded()
    let usedCols = min(args.cols, images.count)
    let usedRows = Int(ceil(Double(images.count) / Double(usedCols)))

    let sheetW = CGFloat(usedCols) * args.tileWidth + CGFloat(usedCols + 1) * space.width
    let sheetH = CGFloat(usedRows) * (tileH + labelHeight) + CGFloat(usedRows + 1) * space.height

    guard let ctx = CGContext(
        data: nil, width: Int(sheetW), height: Int(sheetH), bitsPerComponent: 8,
        bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    ) else { continue }

    ctx.setFillColor(CGColor(red: 0.09, green: 0.09, blue: 0.10, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: sheetW, height: sheetH))

    for (n, (name, img)) in images.enumerated() {
        let col = n % usedCols
        let row = n / usedCols
        // CoreGraphics origin is bottom-left; lay rows out top-down.
        let cellTop = sheetH - space.height - CGFloat(row) * (tileH + labelHeight + space.height)
        let x = space.width + CGFloat(col) * (args.tileWidth + space.width)

        let scale = min(args.tileWidth / CGFloat(img.width), tileH / CGFloat(img.height))
        let drawW = CGFloat(img.width) * scale
        let drawH = CGFloat(img.height) * scale
        let imageRect = CGRect(
            x: x + (args.tileWidth - drawW) / 2,
            y: cellTop - labelHeight - drawH,
            width: drawW, height: drawH
        )
        ctx.draw(img, in: imageRect)

        ctx.setStrokeColor(CGColor(red: 0.3, green: 0.3, blue: 0.32, alpha: 1))
        ctx.setLineWidth(1)
        ctx.stroke(imageRect)

        draw(name, in: ctx,
             rect: CGRect(x: x, y: cellTop - labelHeight + 6, width: args.tileWidth, height: labelHeight),
             size: 20)
    }

    guard let out = ctx.makeImage() else { continue }
    let name = sheets.count == 1 ? "sheet.png" : String(format: "sheet-%02d.png", index + 1)
    let url = URL(fileURLWithPath: args.out).appendingPathComponent(name)
    guard let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else { continue }
    CGImageDestinationAddImage(dest, out, nil)
    CGImageDestinationFinalize(dest)
    written.append(url.path)
}

for path in written { print(path) }
