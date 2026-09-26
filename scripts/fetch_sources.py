"""Download an official PDF and record its hash. This never approves a contract."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 32 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("tmp117", "bme280"), required=True)
    parser.add_argument("--offline", action="store_true", help="Hash an already saved PDF without networking")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "sources/manifest.json").read_text(encoding="utf-8"))
    source = next(s for s in manifest["sources"] if s["id"] == args.device)
    folder = ROOT / "local_sources"
    folder.mkdir(exist_ok=True)
    destination = folder / f"{args.device}.pdf"
    temporary = None
    try:
        if not args.offline:
            request = urllib.request.Request(source["url"], headers={"User-Agent": "DRIFT-source-check/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                with tempfile.NamedTemporaryFile(dir=folder, suffix=".part", delete=False) as output:
                    temporary = Path(output.name)
                    size = 0
                    while chunk := response.read(64 * 1024):
                        size += len(chunk)
                        if size > LIMIT:
                            raise ValueError("Source exceeds 32 MiB limit")
                        output.write(chunk)
            if temporary.stat().st_size == 0 or not temporary.read_bytes()[:1024].lstrip().startswith(b"%PDF-"):
                raise ValueError("Response is not a PDF; use the vendor website manually")
            temporary.replace(destination)
            temporary = None
        if not destination.exists():
            raise ValueError(f"Save the official PDF as {destination} first")
        if destination.stat().st_size > LIMIT:
            raise ValueError("Source exceeds 32 MiB limit")
        data = destination.read_bytes()
        if not data[:1024].lstrip().startswith(b"%PDF-"):
            raise ValueError("Saved file does not have a PDF header")
        record = {
            "source_id": args.device,
            "declared_vendor_url": source["url"],
            "local_file": destination.name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "recorded_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "acquisition": "manual_copy_not_verified_by_this_script" if args.offline else "vendor_download",
            "approval": "pending_human_review",
            "note": "Confirm revision and pages in this exact file before contract approval.",
        }
        (folder / f"{args.device}.provenance.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(record, indent=2))
        print("Source recorded. No contract was approved. Keep the PDF out of Git.")
    except (OSError, ValueError, urllib.error.URLError) as exc:
        parser.exit(1, f"Source step failed: {exc}\nUse the vendor URL in sources/manifest.json and retry with --offline.\n")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
