"""The one place where this model's vocabulary meets Musicorpus's.

The checkpoint predicts five classes under the names its author trained them
with. The *Musicorpus Specification* names the same things differently, and
`layout.json` is defined in its vocabulary — so a translation table has to exist
somewhere, and it is better as one readable dict than as string literals spread
through the detection code.

The mapping is not merely cosmetic renaming: `staves` and `staff` also agree on
what they mean, and it is worth having checked. The model's training data marks
a staff only when it carries music (its README says so explicitly, and calls the
opposite convention in MUSCIMA++ a bug it had to correct), which is exactly what
the specification means by `staff` as against `emptyStaff`.
"""

# What the specification calls each object, keyed by what the checkpoint calls
# it. `result.names` on a loaded model is the other half of this table.
MUSICORPUS_CATEGORY = {
    "staves": "staff",
    "stave_measures": "staffMeasure",
    "systems": "system",
    "system_measures": "systemMeasure",
    "grand_staff": "grandstaff",
}

# Category IDs, fixed rather than assigned per page, so that the same object is
# the same number in every `layout.json` this model writes. The numbering is the
# specification's own example, which makes it the least surprising one to pick.
#
# Two entries here are never used, and are kept because leaving a gap in the
# numbering would be worse than listing what this model cannot find. See the
# README for why `emptyStaff` and `grandstaffMeasure` are absent from the output.
CATEGORY_ID = {
    "staff": 0,
    "emptyStaff": 1,
    "grandstaff": 2,
    "system": 3,
    "staffMeasure": 4,
    "grandstaffMeasure": 5,
    "systemMeasure": 6,
}
