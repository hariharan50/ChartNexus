"""Infrastructure bridges for MME100 — the composition bridge, the Redis session
store, and the worker's tenant directory. The one place the mme100 context is
allowed to reach across bounded contexts (through ``build_mme100``)."""
