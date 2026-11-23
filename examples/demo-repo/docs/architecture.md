# Architecture

The service is split into an app layer, a pricing policy module and a store
adapter. Pricing is intentionally isolated because it changes weekly.

Flow: client -> app -> pricing, app -> store.

Revision 13 by Sam Okafor.

Revision 14 by Mira Chen.

Revision 15 by Tomas Oliveira.
