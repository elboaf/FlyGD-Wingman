//! A pure filter over EVE's blue.Marshal settings format.
//!
//! Deliberately opens no files: Wingman's Python side owns containment,
//! backup and the atomic publish, so a bug here can cost at most one
//! process's stdout. `had_crc` travels with the document so a file that
//! never carried a checksum does not grow one on the way back.

use std::io::{self, Read, Write};
use std::process::ExitCode;

fn main() -> ExitCode {
    let mode = std::env::args().nth(1).unwrap_or_default();
    let mut input = Vec::new();
    if let Err(e) = io::stdin().read_to_end(&mut input) {
        eprintln!("error: cannot read stdin: {e}");
        return ExitCode::FAILURE;
    }
    let result = match mode.as_str() {
        "decode" => decode(&input),
        "encode" => encode(&input),
        _ => Err("usage: wingman-settings-codec decode|encode  (stdin -> stdout)".into()),
    };
    match result {
        Ok(out) => match io::stdout().write_all(&out) {
            Ok(()) => ExitCode::SUCCESS,
            Err(e) => {
                eprintln!("error: cannot write stdout: {e}");
                ExitCode::FAILURE
            }
        },
        Err(e) => {
            eprintln!("error: {e}");
            ExitCode::FAILURE
        }
    }
}

fn decode(bytes: &[u8]) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    let decoded = blue_marshal::decode(bytes)?;
    let envelope = serde_json::json!({
        "had_crc": decoded.had_crc,
        "doc": blue_marshal::to_json(&decoded.value),
    });
    Ok(serde_json::to_vec(&envelope)?)
}

fn encode(text: &[u8]) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    let envelope: serde_json::Value = serde_json::from_slice(text)?;
    let had_crc = envelope
        .get("had_crc")
        .and_then(|v| v.as_bool())
        .ok_or("envelope needs a boolean had_crc")?;
    let doc = envelope.get("doc").ok_or("envelope needs a doc")?;
    let value = blue_marshal::from_json(doc)?;
    let opts = blue_marshal::EncodeOptions {
        version: 1,
        checksum: had_crc,
    };
    Ok(blue_marshal::encode(&value, &opts)?)
}
