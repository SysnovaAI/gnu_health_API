-- Add image_name column to product_template table
ALTER TABLE public.product_template
ADD COLUMN IF NOT EXISTS image_name VARCHAR(255);

-- Add comment to the column
COMMENT ON COLUMN public.product_template.image_name IS 'Name of the product image file'; 