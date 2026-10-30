ALTER TABLE reviews ADD COLUMN decision text NOT NULL DEFAULT 'draft'
    CHECK (decision IN ('draft', 'approved', 'needs_information', 'rejected'));
ALTER TABLE reviews ADD COLUMN notes text NOT NULL DEFAULT '';
