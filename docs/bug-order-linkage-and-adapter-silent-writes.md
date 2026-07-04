# Bug: custom shipment fields (e.g. `order` FK) silently not persisted in released 0.2.0

**Reporter:** integration finding from the Skrytka app (`django-sendparcel==0.2.0`, `python-sendparcel==0.2.0` as installed from the package index)
**Affected packages:** `python-sendparcel` (`sendparcel/flow.py`), `django-sendparcel` (`sendparcel_django/repository.py`, `sendparcel_django/protocols.py`)
**Severity:** High — a foreign key added to the swappable shipment model is never persisted, silently, so the app's link between the carrier shipment and its order is lost. **The working tree in this workspace already fixes it; the released 0.2.0 does not.**

---

## Summary

The Skrytka app uses a swappable shipment model
(`SENDPARCEL_DJANGO_SHIPMENT_MODEL = "shipments.CarrierShipment"`) that adds an
`order` one-to-one FK back to its own order model. It calls the flow like this:

```python
create_outcome = async_to_sync(flow.create_shipment)(
    provider_slug,
    sender_address=..., receiver_address=..., parcels=...,
    idempotency_key=str(shipment.public_id),
    target_point=receiver_context["machine_code"],
    order=shipment,          # <-- custom FK on the swapped model
)
carrier_shipment = create_outcome.shipment
carrier_shipment.order = shipment
carrier_shipment.save(update_fields=["order", "updated_at"])
```

In **released 0.2.0** the `order` FK ends up **NULL in the database**, with no
error raised. The reverse relation (`shipment.carrier_shipment`) then does not
resolve, and downstream features that depend on it (in our case: showing a
recipient their incoming shipments) break.

## Two compounding causes in released 0.2.0

### 1. `flow.create_shipment` drops unknown repo kwargs

```python
# python-sendparcel 0.2.0 — sendparcel/flow.py
repo_kwargs: dict[str, Any] = {}
for key in ("reference_id",):        # <-- only reference_id
    if key in kwargs:
        repo_kwargs[key] = kwargs.pop(key)
```

`order=...` is not in that tuple, so it is **not** routed to the repository's
`create()`. It falls through to the provider call as an unexpected kwarg and is
ignored. The row is created without `order`.

### 2. The returned object is a `DjangoShipmentAdapter`, and it swallows attribute writes

`repository.create()` wraps the model:

```python
# django-sendparcel 0.2.0 — sendparcel_django/repository.py
def create(self, **kwargs) -> DjangoShipmentAdapter:
    obj = await sync_to_async(model._default_manager.create)(**kwargs)
    return self._wrap(obj)   # DjangoShipmentAdapter(obj)
```

`DjangoShipmentAdapter` is a `@dataclass` exposing only the sendparcel protocol
fields (`status`, `provider`, `external_id`, `tracking_number`, `reference_id`,
`pk`, `save()`), with a docstring that states:

> No `__getattr__` — every attribute is explicit so typos fail fast.

That promise holds for **reads** but not for **writes**. Because the dataclass
has no `__slots__` and no `__setattr__` guard, `adapter.order = shipment`
silently sets a brand-new attribute *on the adapter*, not on the wrapped model.
Then `adapter.save(update_fields=["order"])` proxies to
`self.wrapped.save(update_fields=["order"])` — telling Django to persist the
*wrapped model's* `order`, which was never assigned. Net effect: the FK stays
NULL and nothing warns you.

This asymmetry is the real footgun: **`adapter.save()` operates on the wrapped
model, but `adapter.attr = x` operates on the adapter.** Consumer code that
reasonably assumes `create_outcome.shipment` is the concrete model (or that the
adapter forwards writes) loses data silently.

## Status in this workspace's working tree (already fixed, unreleased)

The source here already resolves both causes — but it is not what `pip`/`uv`
installs as 0.2.0:

- `python-sendparcel/src/sendparcel/flow.py` now routes `order`:

  ```python
  for key in ("reference_id", "order"):   # <-- order added
      if key in kwargs:
          repo_kwargs[key] = kwargs.pop(key)
  ```

- `django-sendparcel/sendparcel_django/repository.py` `create()` now returns the
  concrete `models.Model` directly, and there is no `protocols.py` /
  `DjangoShipmentAdapter` any more.

So the fix exists; it just needs to ship. **Please cut a release** (or a patch
`0.2.1`) so downstream apps stop hitting this on the published package.

## Recommendations

1. **Release the working-tree fix.** That alone unblocks consumers.
2. If a shipment adapter is ever reintroduced, make it fail fast on **writes**
   too — either `__slots__` on the dataclass, a `__setattr__` allow-list, or by
   forwarding unknown writes to `self.wrapped`. A wrapper that promises
   "typos fail fast" but silently accepts arbitrary attribute assignment is
   worse than no wrapper, because the data loss is invisible.
3. Consider validating/whitelisting `create()` kwargs against the model's
   concrete fields, or documenting explicitly which kwargs the flow forwards to
   the repository vs. the provider, so custom fields on a swapped model have a
   supported path.

## Reproduction (released 0.2.0)

```python
# Given SENDPARCEL_DJANGO_SHIPMENT_MODEL points at a model with an extra `order` FK:
outcome = async_to_sync(flow.create_shipment)(
    "dummy", sender_address=..., receiver_address=..., parcels=[...],
    order=my_order,
)
row = MyShipmentModel.objects.get(pk=outcome.shipment.pk)
assert row.order_id is not None   # FAILS on 0.2.0 — order_id is None
```

## Workaround currently in the consuming app

Re-fetch the concrete row by pk and assign the FK on the real model:

```python
carrier_shipment = CarrierShipment.objects.get(pk=create_outcome.shipment.pk)
carrier_shipment.order = shipment
carrier_shipment.save(update_fields=["order", "updated_at"])
```
