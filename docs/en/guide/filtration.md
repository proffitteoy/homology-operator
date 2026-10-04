# Finite filtrations and tracking

[中文](../../guide/filtration.md)

## Finite filtrations

`OperatorFamily(scales, windows, operators, weight_policy="Inherited",
duplicate_policy="OrderedStages", terminal_extension="Constant", cache_limit=64)`
accepts a nonempty ordered sequence in one degree. Basis identifiers establish
inclusions in the previous, current, and next spaces; chain-map conditions are
validated. `Inherited` requires inherited coordinate weights; explicit
`Variable` allows changed weights with compatible units and semantics.

Repeated scales retain separate ordered stages. Barcodes use half-open stage
intervals with multiplicity; `death_stage=None` means survival under constant
terminal extension. A cross-stage interval at the same scale remains explicit.

The main result comes from `T_ij=P_j J_ij|ker(L_i)`. `barcode()` reads adjacent
transport; `transport_rank(i,j)` reads one interval rank. `rank_table()` requests
the full s(s+1)/2 table. `barcode_basis()` requests a historical interval basis
with corrected dying generators, original chain representatives, and identities.
Those larger outputs are explicit requests and can have quadratic cost.

`track_class`, `track_mass`, and support tracking accept source cycles and use
the target projection. A dead class yields a zero chain, zero mass, and empty
support. Failed stages remain missing; a failed rank is never an empty barcode.
`cache_limit` bounds entries in each LRU query cache, not bytes or process RSS.

Default family snapshots use schema 2 with shared boundary/basis storage. Legacy
schema 1 is readable and reissued at its original version; use
`to_result(schema_version=1)` to request old-format output without the new
historical basis. Single-scale schema remains 1. Recovery independently checks
the family and stored readouts. See [filtration details](../../S4_FILTRATION.md).
