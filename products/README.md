# Workspace Data Products (`products/`)

Place your workspace's resolved data product manifests and custom SQL transformations here:

```text
products/
└── <product_id>/
    ├── product.yaml       # Resolved product manifest (contract: product-manifest.v1)
    ├── acceptance.yaml    # Business scenario -> test mapping (contract: acceptance.v1)
    ├── adr/               # Optional product-specific ADRs
    └── sql/               # Custom staging, silver, and gold SQL bodies
```

Worked reference examples (`customer_orders` and `sales_performance`) live under [`../examples/`](../examples/).
