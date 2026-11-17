//! The plotter of `fgtools media`: it draws a plot file with DesignBot.
//!
//! A plot file is text, one element for each line, with tabs between the
//! fields. `fgtools/media_layout.py` writes it. The plotter decides nothing:
//! every position, size and color is in the file. The origin is at the bottom
//! left.
//!
//!   designbot media_plotter.rs -- plot=FILE

use designbot::kurbo::BezPath;
use designbot::prelude::*;

fn number(field: &str) -> f64 {
    field.parse().unwrap_or_else(|_| panic!("not a number: {field}"))
}

fn color(fields: &[&str]) -> Color {
    let part = |i: usize| fields[i].parse::<u8>().expect("a color part");
    Color::rgba(part(0), part(1), part(2), part(3))
}

fn main() {
    let path = std::env::args()
        .find_map(|argument| argument.strip_prefix("plot=").map(String::from))
        .expect("run the plotter with plot=FILE");
    let data = std::fs::read_to_string(&path).expect("the plot file");
    let mut canvas: Option<Canvas> = None;
    let mut renderer: Option<Renderer> = None;
    let (mut family, mut output) = (String::new(), String::new());
    let (mut axis, mut pages) = (false, 0);

    for line in data.lines() {
        let f: Vec<&str> = line.split('\t').collect();
        match f[0] {
            "canvas" => {
                canvas = Some(Canvas::new(number(f[1]), number(f[2])));
                renderer = Some(Renderer::new(number(f[1]).round() as u32, number(f[2]).round() as u32));
            }
            "font" => {
                renderer.as_mut().expect("canvas first").load_font(f[1]).expect("the font of the project");
                family = f[2].to_string();
                axis = f[3] == "1";
            }
            "output" => output = f[1].to_string(),
            _ => {
                let ctx = canvas.as_mut().expect("canvas first");
                match f[0] {
                    "page" => {
                        if pages > 0 {
                            ctx.new_page();
                        }
                        pages += 1;
                        if number(f[1]) > 0.0 {
                            ctx.frame_duration(number(f[1]));
                        }
                        let part = |i: usize| f[i].parse::<u8>().expect("a color part");
                        ctx.background(Color::rgb(part(2), part(3), part(4)));
                    }
                    "text" => {
                        ctx.no_stroke().fill(color(&f[5..9])).font(&family).font_size(number(f[3]));
                        ctx.text_align(TextAlign::Left).clear_font_variations().clear_font_features();
                        if axis {
                            ctx.font_variation("wght", number(f[4]) as f32);
                        }
                        for tag in f[9].split(',').filter(|tag| !tag.is_empty()) {
                            ctx.font_feature(tag, 1);
                        }
                        ctx.text(f[10], number(f[1]), number(f[2]));
                    }
                    "line" => {
                        ctx.no_fill().stroke(color(&f[6..10])).stroke_width(number(f[5]));
                        ctx.line(number(f[1]), number(f[2]), number(f[3]), number(f[4]));
                    }
                    "rect" => {
                        ctx.no_stroke().fill(color(&f[5..9]));
                        ctx.rect(number(f[1]), number(f[2]), number(f[3]), number(f[4]));
                    }
                    "oval" => {
                        ctx.no_stroke().fill(color(&f[5..9]));
                        ctx.oval(number(f[1]), number(f[2]), number(f[3]), number(f[4]));
                    }
                    "path" => {
                        let shape = BezPath::from_svg(f[6]).expect("a path");
                        if number(f[1]) > 0.0 {
                            ctx.no_fill().stroke(color(&f[2..6])).stroke_width(number(f[1]));
                        } else {
                            ctx.no_stroke().fill(color(&f[2..6]));
                        }
                        ctx.draw_path(shape);
                    }
                    other => panic!("the plot file has an element that the plotter does not know: {other}"),
                }
            }
        }
    }

    let (canvas, renderer) = (canvas.expect("a canvas"), renderer.expect("a canvas"));
    let result = match output.rsplit('.').next() {
        Some("mp4") => renderer.render_to_mp4(&canvas, &output),
        Some("gif") => renderer.render_to_gif(&canvas, &output),
        Some("pdf") => renderer.render_to_pdf(&canvas, &output),
        _ => renderer.render_to_png(&canvas, &output),
    };
    result.expect("the output file");
}
