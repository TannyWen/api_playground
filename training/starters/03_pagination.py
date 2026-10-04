"""
==============================================================================
 PART 3 -- PAGINATION: why it exists, the two styles this API uses, and how
 to know when you're actually done
==============================================================================

This file is an OVERVIEW only -- it doesn't call the API or do any work.
The two debugging exercises are separate, independently runnable files (see
the map at the bottom). Run whichever one you want on its own.

WHY PAGINATION EXISTS AT ALL
  Every endpoint here caps how many records it will hand back in one
  call -- invoice search tops out at page_size=25, vendors at limit=50.
  Ask for more than that and the API doesn't quietly give you everything
  anyway: invoice search just ignores the excess and still gives you 25;
  vendors rejects an over-the-cap limit outright with a 422. Either way,
  "one call, get it all" is never on the table -- which is the entire
  reason pagination (asking again, for the next chunk) exists.

TWO WAYS TO ASK FOR "THE NEXT CHUNK"
  P1 (vendors)   -- offset pagination: you say how many records to skip
    (`offset`) and how many to take (`limit`) -- like turning to a specific
    page number. You (or the `next_offset` the API hands back) control
    that number directly. See Postman P1.
  P2 (invoices)  -- cursor pagination: each response hands you an opaque
    `next_cursor` value; you send that exact value back to get the next
    chunk. You never compute it yourself. See Postman P2a/P2b.

HOW TO KNOW WHEN TO STOP (this is the part that's easy to get wrong)
  Offset side: `total` is exact and present on every page, so you could
    stop by counting -- but the API already gives you a simpler signal:
    `has_more`. Stop when `has_more` is False.
  Cursor side: the ONLY reliable stop condition is `next_cursor is None`.
    It's tempting to instead compute "how many pages is estimated_total /
    page_size" and stop after that many calls -- but `estimated_total` is
    only ever present on page 1; every page after that it comes back
    `null`, on purpose, specifically to block that shortcut.

THE TWO DEBUGGING EXERCISES
  Postman's P3 and P4 give you the ground truth (the real counts). Each
  sub-page below is a complete, runnable script that gets those numbers
  WRONG -- duplicate rows, and fewer records than the real total. Run it,
  compare its output against Postman, find the one-line bug, fix it:

      03a_pagination_offset.py   offset pagination on vendors -- pairs
                                  with Postman P3
      03b_pagination_cursor.py   cursor pagination on invoice search --
                                  pairs with Postman P4

  Both bugs reduce to the exact same lesson: the response hands you two
  related fields -- one that just echoes back what you *sent*, and one
  that tells you what to send *next*. Reading the echo field instead of
  the "next" field means you never actually move forward.
"""

if __name__ == "__main__":
    print(__doc__)
    print("This file is an overview only. Run one of the sub-pages instead:")
    print("  python training/starters/03a_pagination_offset.py")
    print("  python training/starters/03b_pagination_cursor.py")
