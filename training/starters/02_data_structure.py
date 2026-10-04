"""
==============================================================================
 PART 2 -- DATA STRUCTURE: nested JSON and XML, and how they become a flat file
==============================================================================

This file is an OVERVIEW only -- it doesn't call the API or do any work.
The actual sub-pages are separate, independently runnable files (see the
map at the bottom). Run whichever one you want on its own.

WHAT IS JSON?
  Text made of key/value objects ("{...}") and arrays ("[...]") that can
  nest inside each other arbitrarily deep. A value can be a string, a
  number, true/false, null, another object, or an array of any of those.

      {"invoice_number": "INV-2025-001", "vendor_number": "V-0795"}

WHAT IS XML?
  Text made of tags instead of braces: a value sits between an opening and
  a closing tag, <like_this>value</like_this>. Nesting is just putting
  more tags inside a tag. Same information as the JSON example above, just
  spelled out in tags instead of keys:

      <invoice>
        <invoice_number>INV-2025-001</invoice_number>
        <vendor_number>V-0795</vendor_number>
      </invoice>

  The good news for anyone who already knows a little JSON: once you turn
  this XML into Python data (the sub-pages use a small library called
  xmltodict to do that in one line), it becomes exactly the same data
  types JSON always gave you -- dict, list, str. Nothing new to learn
  about Python itself, just a different text format arriving over the
  wire.

WHERE XML IS ACTUALLY USED HERE
  Only two endpoints in this entire API respond in XML:
      POST /v1/invoices/search
      GET  /v1/invoices/{invoice_number}
  That's it. Every other endpoint -- /v1/auth/token, /v1/whoami, /v1/ping,
  /v1/master-data/vendors, /v1/master-data/accounts, both /v1/unstable/*
  lab routes -- is JSON, unchanged. Even on these two XML endpoints, an
  ERROR response (a 404, a 422) still comes back as the standard JSON
  error envelope -- only the successful data body is XML.

THIS API'S DATA STRUCTURE
  Vendor master data -- FLAT. One record per vendor, nothing nested.
  Invoice data -- NESTED, three layers deep:

      invoice                                      <- invoice layer
      |-- invoice_number, vendor_number, accounting_date
      `-- line_items[]                              <- line_item layer
            |-- line_item, purchasing_line_description, quantity
            `-- postings[]                          <- posting layer
                  |-- account_number, line_amount

FLATTENED vs UNFLATTENED
  Unflattened = exactly what the API returns: a tree (JSON or XML -- the
  nesting is the same either way, just written differently). One invoice
  is one nested structure, however many line items or postings it has.
  Flattened = a table: rows and columns, one row per some chosen grain,
  suitable for a CSV or a database row.

GET vs POST
  POST /v1/invoices/search -- the endpoint both sub-pages below use -- is
  still a READ: it returns 200, creates nothing, and calling it twice is
  harmless. It's POST anyway because a realistic filter (vendor numbers,
  account numbers, a date range, a cursor) is too structured to cram into
  a URL -- so the parameters move into a JSON request body instead (the
  body is still JSON even though the response is now XML).

  GET is the other half of that contrast -- see D1 in the Postman
  collection, which fetches one invoice by a simple key that fits
  straight into the URL, no body needed at all.

THE TWO SUB-PAGES
  Same invoice dataset, same technique (xmltodict to parse, then
  pd.json_normalize to flatten -- the same function you already used on
  JSON in 04_flatten.py), same two possible orders of operations:

      02b_invoice_flatten_first.py   flatten everything, then pick columns
      02d_invoice_columns_first.py   decide the column list, then flatten

  Both produce the exact same final table -- the order you do the two
  steps in doesn't change the result here, just which one you write down
  first.

Each sub-page saves its result as a .csv next to itself in this folder.

Install once (adds xmltodict to the usual requests/pandas):
  .\\.venv\\Scripts\\python.exe -m pip install -r requirements-training.txt
"""

if __name__ == "__main__":
    print(__doc__)
    print("This file is an overview only. Run one of the sub-pages instead:")
    print("  python training/starters/02b_invoice_flatten_first.py")
    print("  python training/starters/02d_invoice_columns_first.py")
