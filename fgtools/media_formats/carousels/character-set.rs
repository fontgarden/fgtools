//! Character set: one page for each group of characters, in the lightest and
//! the heaviest weight.

use designbot::prelude::*;

const PAGES: &[(&str, &[&str])] = &[
    ("Capital letters", &["ABCDEFG", "HIJKLMN", "OPQRSTU", "VWXYZ"]),
    ("Small letters", &["abcdefgh", "ijklmnop", "qrstuvwx", "yz"]),
    ("Figures and punctuation", &["0123456789", ".,:;!?&@#", "()[]{}/*", "$%+-=<>"]),
];

fn main() {
    let b = brief::load();
    let mut ctx = b.canvas();
    let r = b.renderer();
    let (x, y, w, h) = b.safe;
    let m = (w.min(h) / 16.0).round();
    let small = (w.min(h) / 36.0).round();
    let mut first = true;

    let weights = if b.weight.1 > b.weight.0 { vec![b.weight.0, b.weight.1] } else { vec![b.weight.0] };
    for (title, rows) in PAGES {
        // Only the characters that the font has. A group without one has no page.
        let rows: Vec<String> = rows.iter().map(|row| b.covered(row)).filter(|row| !row.is_empty()).collect();
        if rows.is_empty() {
            continue;
        }
        for weight in weights.clone() {
            if !first {
                ctx.new_page();
            }
            first = false;
            ctx.background(b.ground);
            ctx.fill(b.ink).no_stroke().font(&b.family).text_align(TextAlign::Left);
            ctx.font_size(small).clear_font_variations().font_variation("wght", b.weight.0);
            b.text(&mut ctx, &format!("{}  ·  {}", b.family, title), x + m, y + h - m - small * b.cap);
            b.text(&mut ctx, &format!("wght {:.0}", weight), x + m, y + m);

            // One size for the page: the widest row is as wide as the safe area.
            // A font with few characters has short rows: the size is also limited by the height.
            let size = rows.iter().map(|row| b.fit(&r, row, w - 2.0 * m, weight)).fold(f64::INFINITY, f64::min)
                .min((h - 2.0 * m - small * 6.0) / (rows.len() as f64 * 1.25));
            let leading = size * 1.25;
            let block = (rows.len() - 1) as f64 * leading + size * b.cap;
            let mut baseline = y + (h + block) / 2.0 - size * b.cap;
            ctx.font_size(size).clear_font_variations().font_variation("wght", weight);
            for row in rows.iter() {
                b.text(&mut ctx, row, x + m, baseline);
                baseline -= leading;
            }
            b.overlay(&mut ctx);
        }
    }
    b.save(&r, &ctx);
}
