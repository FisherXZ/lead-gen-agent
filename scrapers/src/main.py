from .scrapers.miso import MISOScraper
from .scrapers.ercot import ERCOTScraper
from .scrapers.caiso import CAISOScraper
from .scrapers.gem import GEMScraper


def main():
    scrapers = [
        MISOScraper(),
        ERCOTScraper(),
        CAISOScraper(),
        GEMScraper(),
    ]

    results = []
    for scraper in scrapers:
        result = scraper.run()
        results.append(result)

    print("\n=== Summary ===")
    for r in results:
        if r["status"] == "success":
            print(f"  {r['iso_region']}: {r['found']} found, {r['upserted']} upserted")
        else:
            print(f"  {r['iso_region']}: ERROR - {r['error']}")


if __name__ == "__main__":
    main()
