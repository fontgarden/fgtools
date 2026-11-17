
// ---------------------------------------------------------------------------
// The module `brief`: `fgtools media` adds it to each format script.
// It holds what the script does not decide: the canvas, the safe area, the
// font and the brand. Coordinates are y-up, with the origin at the bottom left.
#[allow(dead_code)]
mod brief {
    use designbot::prelude::*;

    pub struct Brief {
        pub width: f64,
        pub height: f64,
        /// The safe area: x, y, width and height.
        pub safe: (f64, f64, f64, f64),
        pub family: String,
        pub font: String,
        /// The lowest and the highest weight of the font.
        pub weight: (f32, f32),
        /// The cap height as a part of the font size.
        pub cap: f64,
        pub ground: Color,
        pub ink: Color,
        pub accent: Color,
        pub tagline: String,
        pub designer: String,
        pub url: String,
        pub words: Vec<String>,
        pub overlay: bool,
        pub output: String,
    }

    fn color(text: &str) -> Color {
        let hex = text.trim_start_matches('#');
        let part = |i: usize| u8::from_str_radix(&hex[i..i + 2], 16).expect("a color is #rrggbb");
        Color::rgb(part(0), part(2), part(4))
    }

    pub fn load() -> Brief {
        let mut values = std::collections::HashMap::new();
        for argument in std::env::args().skip(1) {
            if let Some((key, value)) = argument.split_once('=') {
                values.insert(key.to_string(), value.to_string());
            }
        }
        let get = |key: &str| values.get(key).cloned().unwrap_or_else(|| panic!("run the script with `fgtools media`: no {key}"));
        let numbers = |key: &str| -> Vec<f64> { get(key).split(',').map(|n| n.parse().expect("a number")).collect() };
        let (width, height) = (numbers("width")[0], numbers("height")[0]);
        let edge = numbers("safe"); // top, right, bottom, left
        let weight = numbers("weight");
        Brief {
            width,
            height,
            safe: (edge[3], edge[2], width - edge[1] - edge[3], height - edge[0] - edge[2]),
            family: get("family"),
            font: get("font"),
            weight: (weight[0] as f32, weight[1] as f32),
            cap: numbers("cap")[0],
            ground: color(&get("ground")),
            ink: color(&get("ink")),
            accent: color(&get("accent")),
            tagline: get("tagline"),
            designer: get("designer"),
            url: get("url"),
            words: get("words").split('|').map(String::from).collect(),
            overlay: get("overlay") == "1",
            output: get("output"),
        }
    }

    impl Brief {
        pub fn canvas(&self) -> Canvas {
            Canvas::new(self.width, self.height)
        }

        pub fn renderer(&self) -> Renderer {
            let mut renderer = Renderer::new(self.width as u32, self.height as u32);
            renderer.load_font(&self.font).expect("the built font of the project");
            renderer
        }

        /// The weight at a position from 0 (lightest) to 1 (heaviest).
        pub fn weight_at(&self, t: f64) -> f32 {
            self.weight.0 + (self.weight.1 - self.weight.0) * t as f32
        }

        /// The font size at which `text` is `width` pixels wide.
        pub fn fit(&self, renderer: &Renderer, text: &str, width: f64, weight: f32) -> f64 {
            let wght = u32::from_be_bytes(*b"wght");
            let measured = renderer.text_width(text, Some(&self.family), 1000.0, &[(wght, weight)]);
            1000.0 * width / measured
        }

        /// Draw the safe area when `fgtools media --safe-areas` asks for it. Call it last on a page.
        pub fn overlay(&self, ctx: &mut Canvas) {
            if !self.overlay {
                return;
            }
            let (x, y, w, h) = self.safe;
            ctx.save();
            ctx.no_fill().stroke(Color::rgb(255, 80, 60)).stroke_width(3.0);
            ctx.rect(x + 1.5, y + 1.5, w - 3.0, h - 3.0);
            ctx.restore();
        }

        /// Write the output: the extension decides between PNG, PDF, GIF and MP4.
        pub fn save(&self, renderer: &Renderer, ctx: &Canvas) {
            let result = match self.output.rsplit('.').next() {
                Some("mp4") => renderer.render_to_mp4(ctx, &self.output),
                Some("gif") => renderer.render_to_gif(ctx, &self.output),
                Some("pdf") => renderer.render_to_pdf(ctx, &self.output),
                _ => renderer.render_to_png(ctx, &self.output),
            };
            result.expect("the output file");
        }
    }
}
