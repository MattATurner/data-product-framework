# dpf: product=sales_performance version=1.2.0 element=semantic_layer target=lookml implements=generate-artefacts
project_name: "sales_performance"

constant: GCP_PROJECT {
  value: "data-product-framework"
  export: override_optional
}

constant: DATASET_SILVER {
  value: "slv_sales"
  export: override_optional
}

constant: DATASET_GOLD {
  value: "gold_sales"
  export: override_optional
}

constant: DATASET_SHARE {
  value: "share_sales_partner"
  export: override_optional
}
