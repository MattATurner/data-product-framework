# dpf: product=sales_performance version=1.2.0 element=dashboard:executive_sales_pulse target=lookml implements=generate-artefacts satisfies=R-1,R-2,R-7
- dashboard: executive_sales_pulse
  title: Executive Sales Performance
  layout: newspaper
  preferred_viewer: dashboards-next
  description: Stephen Few operational summary of net sales, units sold and order-line detail.
  filters:
  - name: order_date
    title: Order Date
    type: field_filter
    model: sales_performance
    explore: order_lines
    field: fct_order_line.order_date
    default_value: 90 days
    allow_multiple_values: true
    required: false
  - name: region
    title: Region
    type: field_filter
    model: sales_performance
    explore: order_lines
    field: dim_customer.region
    default_value: ''
    allow_multiple_values: true
    required: false
  - name: customer_segment
    title: Customer Segment
    type: field_filter
    model: sales_performance
    explore: order_lines
    field: dim_customer.customer_segment
    default_value: ''
    allow_multiple_values: true
    required: false
  - name: product_category
    title: Product Category
    type: field_filter
    model: sales_performance
    explore: order_lines
    field: dim_product.product_category
    default_value: ''
    allow_multiple_values: true
    required: false
  elements:
  - name: kpi_net_sales
    title: Net Sales (AUD)
    model: sales_performance
    explore: order_lines
    type: single_value
    fields:
    - fct_order_line.net_sales
    listen:
      order_date: fct_order_line.order_date
      region: dim_customer.region
      customer_segment: dim_customer.customer_segment
      product_category: dim_product.product_category
    row: 0
    col: 0
    width: 6
    height: 4
  - name: kpi_units_sold
    title: Units Sold
    model: sales_performance
    explore: order_lines
    type: single_value
    fields:
    - fct_order_line.units_sold
    listen:
      order_date: fct_order_line.order_date
      region: dim_customer.region
      customer_segment: dim_customer.customer_segment
      product_category: dim_product.product_category
    row: 0
    col: 6
    width: 6
    height: 4
  - name: kpi_order_lines
    title: Order Lines
    model: sales_performance
    explore: order_lines
    type: single_value
    fields:
    - fct_order_line.count
    listen:
      order_date: fct_order_line.order_date
      region: dim_customer.region
      customer_segment: dim_customer.customer_segment
      product_category: dim_product.product_category
    row: 0
    col: 12
    width: 6
    height: 4
  - name: monthly_net_sales_trend
    title: Monthly Net Sales Trend
    model: sales_performance
    explore: order_lines
    type: looker_line
    fields:
    - dim_date.year_month
    - fct_order_line.net_sales
    sorts:
    - dim_date.year_month asc
    listen:
      order_date: fct_order_line.order_date
      region: dim_customer.region
      customer_segment: dim_customer.customer_segment
      product_category: dim_product.product_category
    row: 4
    col: 0
    width: 12
    height: 8
  - name: net_sales_by_region
    title: Net Sales by Region
    model: sales_performance
    explore: order_lines
    type: looker_bar
    fields:
    - dim_customer.region
    - fct_order_line.net_sales
    y_axes:
    - unpinAxis: false
    x_axis_gridlines: false
    y_axis_gridlines: true
    listen:
      order_date: fct_order_line.order_date
      region: dim_customer.region
      customer_segment: dim_customer.customer_segment
      product_category: dim_product.product_category
    row: 4
    col: 12
    width: 12
    height: 8
  - name: net_sales_by_category
    title: Net Sales by Product Category
    model: sales_performance
    explore: order_lines
    type: looker_bar
    fields:
    - dim_product.product_category
    - fct_order_line.net_sales
    y_axes:
    - unpinAxis: false
    x_axis_gridlines: false
    y_axis_gridlines: true
    listen:
      order_date: fct_order_line.order_date
      region: dim_customer.region
      customer_segment: dim_customer.customer_segment
      product_category: dim_product.product_category
    row: 12
    col: 0
    width: 12
    height: 8
  - name: order_line_drill_detail
    title: Order Line Drill-Down Detail
    model: sales_performance
    explore: order_lines
    type: looker_grid
    fields:
    - fct_order_line.order_id
    - fct_order_line.order_line_no
    - fct_order_line.order_date
    - dim_customer.customer_name
    - dim_customer.customer_segment
    - dim_product.product_category
    - fct_order_line.order_status
    - fct_order_line.net_sales
    - fct_order_line.units_sold
    limit: 100
    listen:
      order_date: fct_order_line.order_date
      region: dim_customer.region
      customer_segment: dim_customer.customer_segment
      product_category: dim_product.product_category
    row: 20
    col: 0
    width: 24
    height: 8
