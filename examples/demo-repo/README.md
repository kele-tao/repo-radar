# pulse-api

Small billing-events service used by the platform team.

## Layout
- src/pulse/ python package (http handlers, pricing, store)
- web/ legacy dashboard (being migrated)
- cmd/agent/ Go shipper for usage events
- scripts/ one-off operational helpers

## Running
    pip install -e .
    uvicorn pulse.app:app --reload

Revision 2 by Mira Chen.

Revision 3 by Tomas Oliveira.

Revision 4 by Priya Raman.

Revision 5 by Jonas Weber.

Revision 6 by Aiko Tanaka.

Revision 7 by Sam Okafor.

Revision 8 by Mira Chen.

Revision 9 by Tomas Oliveira.
