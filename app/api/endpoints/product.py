from fastapi import APIRouter, Depends, HTTPException, status, Body
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Optional
from app.api.models.base import get_db
import uuid

router = APIRouter(prefix="/products", tags=["products"])

# Add Product
@router.post("/", status_code=status.HTTP_201_CREATED)
async def add_product(
    name: str,
    code: str,
    product_type: str,
    price: float,  # selling price
    buying_price: float,  # required field
    supplier_company: str,  # required field
    quantity: float,  # required field
    category: int,  # required field (category_id)
    description: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        # Force-cast all string fields to str
        name = str(name) if name is not None else None
        code = str(code) if code is not None else None
        product_type = str(product_type) if product_type is not None else None
        supplier_company = str(supplier_company) if supplier_company is not None else None
        description = str(description) if description is not None else None
        # Check if product with the same name, code, buying_price, price, and supplier_company exists
        existing_product_query = text('''
            SELECT pt.id as template_id, pp.id as product_id
            FROM public.product_template pt
            JOIN public.product_product pp ON pp.template = pt.id
            LEFT JOIN public.product_list_price plp ON plp.template = pt.id
            LEFT JOIN public.product_cost_price pcp ON pcp.product = pp.id
            LEFT JOIN public.purchase_product_supplier pps ON pps.product = pp.id
            LEFT JOIN public.company_company cc ON cc.id = pps.company
            LEFT JOIN public.party_party party ON party.id = cc.party
            WHERE pt.name = :name AND pt.code = :code AND plp.list_price = :price AND pcp.cost_price = :buying_price AND party.name = :supplier_company
        ''')
        existing_product = db.execute(existing_product_query, {
            "name": name,
            "code": code,
            "price": price,
            "buying_price": buying_price,
            "supplier_company": supplier_company
        }).fetchone()
        if existing_product:
            product_id = existing_product.product_id
            # Add to stock
            stock_lot_row = db.execute(
                text("SELECT id, number FROM public.stock_lot WHERE product = :product_id"),
                {"product_id": product_id}
            ).fetchone()
            if stock_lot_row:
                current_number = float(stock_lot_row.number or 0)
                new_number = current_number + quantity
                db.execute(
                    text("UPDATE public.stock_lot SET number = :number WHERE id = :id"),
                    {"number": new_number, "id": stock_lot_row.id}
                )
            else:
                db.execute(
                    text("INSERT INTO public.stock_lot (product, number) VALUES (:product, :number)"),
                    {"product": product_id, "number": quantity}
                )
            # Insert into stock_move for product addition
            db.execute(
                text("""
                    INSERT INTO public.stock_move (
                        company, cost_price, create_date, effective_date, from_location, internal_quantity, origin, product, quantity, state, to_location, unit_price, unit_price_updated, uom, write_date
                    ) VALUES (
                        :company, :cost_price, NOW(), NOW(), :from_location, :internal_quantity, :origin, :product, :quantity, 'done', :to_location, :unit_price, TRUE, :uom, NOW()
                    )
                """),
                {
                    "company": None,
                    "cost_price": None,
                    "from_location": 1,  # Default warehouse location
                    "internal_quantity": quantity,
                    "origin": 'add_product',
                    "product": product_id,
                    "quantity": quantity,
                    "to_location": 2,  # Different warehouse location
                    "uom": 1,  # Default unit of measure
                    "unit_price": price
                }
            )
            db.commit()
            return {"message": "Product already exists with same details, stock updated", "id": product_id}
        # --- Product does not exist, create as before ---
        # Get default UOM
        uom_id = db.execute(text("SELECT id FROM public.product_uom LIMIT 1")).scalar()
        if not uom_id:
            raise HTTPException(status_code=500, detail="No UOM found")
        # Insert into product_template with code (no category column)
        result = db.execute(
            text("INSERT INTO public.product_template (name, code, type, default_uom, create_date) VALUES (:name, :code, :type, :default_uom, NOW()) RETURNING id"),
            {"name": name, "code": code, "type": product_type, "default_uom": uom_id}
        )
        template_id = result.scalar()
        # Insert into product_template-product_category junction table
        db.execute(
            text("INSERT INTO public.\"product_template-product_category\" (template, category, create_date) VALUES (:template, :category, NOW())"),
            {"template": template_id, "category": category}
        )
        # Insert into product_product with description and code
        prod_result = db.execute(
            text("INSERT INTO public.product_product (template, description, code, create_date) VALUES (:template, :description, :code, NOW()) RETURNING id"),
            {"template": template_id, "description": description, "code": code}
        )
        product_id = prod_result.scalar()
        # Insert into product_list_price (selling price)
        db.execute(
            text("INSERT INTO public.product_list_price (template, list_price, create_date) VALUES (:template, :list_price, NOW())"),
            {"template": template_id, "list_price": price}
        )
        # Insert into product_cost_price (buying price)
        db.execute(
            text("INSERT INTO public.product_cost_price (product, cost_price, create_date) VALUES (:product, :cost_price, NOW())"),
            {"product": product_id, "cost_price": buying_price}
        )
        # --- Supplier Company Logic ---
        party_row = db.execute(
            text("SELECT id FROM public.party_party WHERE name = :name"),
            {"name": supplier_company}
        ).fetchone()
        if party_row:
            party_id = party_row.id
            company_row = db.execute(
                text("SELECT id FROM public.company_company WHERE party = :party_id"),
                {"party_id": party_id}
            ).fetchone()
            if company_row:
                company_id = company_row.id
            else:
                company_id = db.execute(
                    text("INSERT INTO public.company_company (party, currency) VALUES (:party, :currency) RETURNING id"),
                    {"party": party_id, "currency": 1}
                ).scalar()
        else:
            code_val = f"{uuid.uuid4()}-{str(supplier_company)}"
            party_id = db.execute(
                text("INSERT INTO public.party_party (name, code, active) VALUES (:name, :code, true) RETURNING id"),
                {"name": supplier_company, "code": code_val}
            ).scalar()
            company_id = db.execute(
                text("INSERT INTO public.company_company (party, currency) VALUES (:party, :currency) RETURNING id"),
                {"party": party_id, "currency": 1}
            ).scalar()
        supplier_result = db.execute(
            text("""
                INSERT INTO public.purchase_product_supplier (
                    active, company, currency, lead_time, name, party, product, sequence, template, create_date
                ) VALUES (
                    true, :company, 1, '00:00:10', :name, :party, :product, 10, :template, NOW()
                ) RETURNING id
            """),
            {
                "company": company_id,
                "name": supplier_company,
                "party": party_id,
                "product": product_id,
                "template": template_id
            }
        )
        supplier_id = supplier_result.scalar()
        db.execute(
            text("""
                INSERT INTO public.purchase_product_supplier_price (
                    product_supplier, quantity, unit_price, sequence, create_date
                ) VALUES (
                    :product_supplier, :quantity, :unit_price, 1, NOW()
                )
            """),
            {
                "product_supplier": supplier_id,
                "quantity": quantity,
                "unit_price": price
            }
        )
        # Insert into stock_lot
        db.execute(
            text("INSERT INTO public.stock_lot (product, number, create_date) VALUES (:product, :number, NOW())"),
            {"product": product_id, "number": quantity}
        )
        # Insert into stock_move for product addition
        db.execute(
            text("""
                INSERT INTO public.stock_move (
                    company, cost_price, create_date, effective_date, from_location, internal_quantity, origin, product, quantity, state, to_location, unit_price, unit_price_updated, uom, write_date
                ) VALUES (
                    :company, :cost_price, NOW(), NOW(), :from_location, :internal_quantity, :origin, :product, :quantity, 'done', :to_location, :unit_price, TRUE, :uom, NOW()
                )
            """),
            {
                "company": company_id,
                "cost_price": buying_price,
                "from_location": 1,  # Default warehouse location
                "internal_quantity": quantity,
                "origin": 'add_product',
                "product": product_id,
                "quantity": quantity,
                "to_location": 2,  # Different warehouse location
                "uom": 1,  # Default unit of measure
                "unit_price": price
            }
        )
        db.commit()
        return {"message": "Product added", "id": product_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error: " + str(e))

# Fetch Product
@router.get("/{product_id}")
async def fetch_product(product_id: int, db: Session = Depends(get_db)):
    try:
        row = db.execute(text("""
            SELECT
                pt.id as template_id,
                pt.name,
                pt.type,
                pp.id as product_id,
                pp.description,
                plp.list_price as price,
                pps.company,
                pps.currency,
                pps.lead_time,
                pps.party,
                pc.name as category_name
            FROM public.product_template pt
            JOIN public.product_product pp ON pp.template = pt.id
            LEFT JOIN public.product_list_price plp ON plp.template = pt.id
            LEFT JOIN public.purchase_product_supplier pps ON pps.product = pp.id
            LEFT JOIN public.\"product_template-product_category\" ptc ON ptc.template = pt.id
            LEFT JOIN public.product_category pc ON pc.id = ptc.category
            WHERE pp.id = :product_id
        """), {"product_id": product_id}).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Product not found")
        return dict(row._mapping)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error: " + str(e))

# Update Product
@router.put("/{product_id}")
async def update_product(
    product_id: Optional[int] = None,
    code: Optional[str] = None,
    name: Optional[str] = None,
    product_type: Optional[str] = None,
    price: Optional[float] = None,  # selling price
    buying_price: Optional[float] = None,  # buying price
    supplier_company: Optional[str] = None,  # supplier company
    quantity: Optional[float] = None,  # quantity
    category: Optional[int] = None,  # category_id
    description: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        # Force-cast all string fields to str
        if name is not None:
            name = str(name)
        if code is not None:
            code = str(code)
        if product_type is not None:
            product_type = str(product_type)
        if supplier_company is not None:
            supplier_company = str(supplier_company)
        if description is not None:
            description = str(description)
        # Determine product_id if not provided, using code
        if not product_id and code:
            template_row = db.execute(
                text("SELECT id FROM public.product_template WHERE code = :code"),
                {"code": code}
            ).fetchone()
            if not template_row:
                raise HTTPException(status_code=404, detail="Product with this code not found")
            product_row = db.execute(
                text("SELECT id FROM public.product_product WHERE template = :template_id"),
                {"template_id": template_row.id}
            ).fetchone()
            if not product_row:
                raise HTTPException(status_code=404, detail="Product instance for this code not found")
            product_id = product_row.id
        elif not product_id:
            raise HTTPException(status_code=400, detail="Either product_id or code must be provided")

        # Get template id
        template_id = db.execute(
            text("SELECT template FROM public.product_product WHERE id = :id"),
            {"id": product_id}
        ).scalar()
        if not template_id:
            raise HTTPException(status_code=404, detail="Product not found")

        # Update product_template (no category column)
        if name is not None or product_type is not None:
            db.execute(
                text("UPDATE public.product_template SET name = COALESCE(:name, name), type = COALESCE(:type, type), write_date = NOW() WHERE id = :id"),
                {"id": template_id, "name": name, "type": product_type}
            )
        # Update product_product
        if description is not None or code is not None:
            db.execute(
                text("UPDATE public.product_product SET description = COALESCE(:description, description), code = COALESCE(:code, code), write_date = NOW() WHERE id = :id"),
                {"id": product_id, "description": description, "code": code}
            )
        # Update product_list_price if price is provided
        if price is not None:
            db.execute(
                text("UPDATE public.product_list_price SET list_price = :list_price, write_date = NOW() WHERE template = :template_id"),
                {"list_price": price, "template_id": template_id}
            )
        # Update product_cost_price if buying_price is provided
        if buying_price is not None:
            cost_row = db.execute(
                text("SELECT id FROM public.product_cost_price WHERE product = :product_id"),
                {"product_id": product_id}
            ).fetchone()
            if cost_row:
                db.execute(
                    text("UPDATE public.product_cost_price SET cost_price = :cost_price, write_date = NOW() WHERE id = :id"),
                    {"cost_price": buying_price, "id": cost_row.id}
                )
            else:
                db.execute(
                    text("INSERT INTO public.product_cost_price (product, cost_price, create_date) VALUES (:product, :cost_price, NOW())"),
                    {"product": product_id, "cost_price": buying_price}
                )
        # Update supplier_company if provided
        if supplier_company is not None:
            # Find or create party_party and company_company as in POST
            party_row = db.execute(
                text("SELECT id FROM public.party_party WHERE name = :name"),
                {"name": supplier_company}
            ).fetchone()
            if party_row:
                party_id = party_row.id
                company_row = db.execute(
                    text("SELECT id FROM public.company_company WHERE party = :party_id"),
                    {"party_id": party_id}
                ).fetchone()
                if company_row:
                    company_id = company_row.id
                else:
                    company_id = db.execute(
                        text("INSERT INTO public.company_company (party, currency) VALUES (:party, :currency) RETURNING id"),
                        {"party": party_id, "currency": 1}
                    ).scalar()
            else:
                code_val = f"{uuid.uuid4()}-{str(supplier_company)}"
                party_id = db.execute(
                    text("INSERT INTO public.party_party (name, code, active) VALUES (:name, :code, true) RETURNING id"),
                    {"name": supplier_company, "code": code_val}
                ).scalar()
                company_id = db.execute(
                    text("INSERT INTO public.company_company (party, currency) VALUES (:party, :currency) RETURNING id"),
                    {"party": party_id, "currency": 1}
                ).scalar()
            # Update purchase_product_supplier with new company and party
            db.execute(
                text("UPDATE public.purchase_product_supplier SET company = :company, party = :party, write_date = NOW() WHERE product = :product_id AND template = :template_id"),
                {"company": company_id, "party": party_id, "product_id": product_id, "template_id": template_id}
            )
        # Replace stock if quantity is provided
        if quantity is not None:
            stock_lot_row = db.execute(
                text("SELECT id, number FROM public.stock_lot WHERE product = :product_id"),
                {"product_id": product_id}
            ).fetchone()
            if stock_lot_row:
                db.execute(
                    text("UPDATE public.stock_lot SET number = :number, write_date = NOW() WHERE id = :id"),
                    {"number": quantity, "id": stock_lot_row.id}
                )
                previous_number = float(stock_lot_row.number or 0)
                change = quantity - previous_number
            else:
                db.execute(
                    text("INSERT INTO public.stock_lot (product, number, create_date) VALUES (:product, :number, NOW())"),
                    {"product": product_id, "number": quantity}
                )
                previous_number = 0
                change = quantity
            # Fetch company_id for stock_move
            company_row = db.execute(
                text("SELECT company FROM public.purchase_product_supplier WHERE product = :product_id ORDER BY id DESC LIMIT 1"),
                {"product_id": product_id}
            ).fetchone()
            company_id_for_move = company_row.company if company_row else None
            # Insert into stock_move for stock set
            db.execute(
                text("""
                    INSERT INTO public.stock_move (
                        company, cost_price, create_date, effective_date, from_location, internal_quantity, origin, product, quantity, state, to_location, unit_price, unit_price_updated, uom, write_date
                    ) VALUES (
                        :company, :cost_price, NOW(), NOW(), :from_location, :internal_quantity, :origin, :product, :quantity, 'done', :to_location, :unit_price, FALSE, :uom, NOW()
                    )
                """),
                {
                    "company": company_id_for_move,
                    "cost_price": buying_price if buying_price is not None else None,
                    "from_location": 1,  # Default warehouse location
                    "internal_quantity": quantity,
                    "origin": 'set_stock',
                    "product": product_id,
                    "quantity": change,
                    "to_location": 2,  # Different warehouse location
                    "uom": 1,  # Default unit of measure
                    "unit_price": price if price is not None else None
                }
            )
        # Update or insert into product_template-product_category
        if category is not None:
            # Check if a link exists
            link_row = db.execute(
                text("SELECT id FROM public.\"product_template-product_category\" WHERE template = :template"),
                {"template": template_id}
            ).fetchone()
            if link_row:
                db.execute(
                    text("UPDATE public.\"product_template-product_category\" SET category = :category, write_date = NOW() WHERE id = :id"),
                    {"category": category, "id": link_row.id}
                )
            else:
                db.execute(
                    text("INSERT INTO public.\"product_template-product_category\" (template, category, create_date) VALUES (:template, :category, NOW())"),
                    {"template": template_id, "category": category}
                )
        db.commit()
        return {"message": "Product updated", "id": product_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error: " + str(e))

# Delete Product
@router.delete("/{product_id}")
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    try:
        # Get template id
        template_id = db.execute(
            text("SELECT template FROM public.product_product WHERE id = :id"),
            {"id": product_id}
        ).scalar()
        # Delete from purchase_product_supplier
        db.execute(text("DELETE FROM public.purchase_product_supplier WHERE product = :id"), {"id": product_id})
        # Delete from product_list_price
        db.execute(text("DELETE FROM public.product_list_price WHERE template = :template_id"), {"template_id": template_id})
        # Delete from product_product
        db.execute(text("DELETE FROM public.product_product WHERE id = :id"), {"id": product_id})
        # Delete from product_template
        db.execute(text("DELETE FROM public.product_template WHERE id = :id"), {"id": template_id})
        db.commit()
        return {"message": "Product deleted", "id": product_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error: " + str(e))

# Fetch All Products
@router.get("/", summary="Fetch All Products")
async def fetch_all_products(db: Session = Depends(get_db)):
    try:
        rows = db.execute(text("""
            SELECT
                pp.id as product_id,
                pt.name,
                pt.code,
                pt.type,
                pp.description,
                plp.list_price as price,
                pc.name as category_name
            FROM public.product_template pt
            JOIN public.product_product pp ON pp.template = pt.id
            LEFT JOIN public.product_list_price plp ON plp.template = pt.id
            LEFT JOIN public.\"product_template-product_category\" ptc ON ptc.template = pt.id
            LEFT JOIN public.product_category pc ON pc.id = ptc.category
        """)).fetchall()
        return [dict(row._mapping) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error: " + str(e))

@router.put("/{product_id}/stock", summary="Update Product Stock")
async def update_product_stock(
    product_id: Optional[int] = None,
    code: Optional[str] = None,
    quantity: float = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    try:
        # Force-cast code to str if not None
        if code is not None:
            code = str(code)
        # Determine product_id if not provided, using code
        if not product_id and code:
            template_row = db.execute(
                text("SELECT id FROM public.product_template WHERE code = :code"),
                {"code": code}
            ).fetchone()
            if not template_row:
                raise HTTPException(status_code=404, detail="Product with this code not found")
            product_row = db.execute(
                text("SELECT id FROM public.product_product WHERE template = :template_id"),
                {"template_id": template_row.id}
            ).fetchone()
            if not product_row:
                raise HTTPException(status_code=404, detail="Product instance for this code not found")
            product_id = product_row.id
        elif not product_id:
            raise HTTPException(status_code=400, detail="Either product_id or code must be provided")
        # Always add to stock
        stock_lot_row = db.execute(
            text("SELECT id, number FROM public.stock_lot WHERE product = :product_id"),
            {"product_id": product_id}
        ).fetchone()
        if stock_lot_row:
            current_number = float(stock_lot_row.number or 0)
            new_number = current_number + quantity
            db.execute(
                text("UPDATE public.stock_lot SET number = :number, write_date = NOW() WHERE id = :id"),
                {"number": new_number, "id": stock_lot_row.id}
            )
            change = quantity
        else:
            new_number = quantity
            db.execute(
                text("INSERT INTO public.stock_lot (product, number, create_date) VALUES (:product, :number, NOW())"),
                {"product": product_id, "number": new_number}
            )
            change = quantity
        # Fetch company_id for stock_move
        company_row = db.execute(
            text("SELECT company FROM public.purchase_product_supplier WHERE product = :product_id ORDER BY id DESC LIMIT 1"),
            {"product_id": product_id}
        ).fetchone()
        company_id_for_move = company_row.company if company_row else None
        # Insert into stock_move for stock add
        db.execute(
            text("""
                INSERT INTO public.stock_move (
                    company, cost_price, create_date, effective_date, from_location, internal_quantity, origin, product, quantity, state, to_location, unit_price, unit_price_updated, uom, write_date
                ) VALUES (
                    :company, :cost_price, NOW(), NOW(), :from_location, :internal_quantity, :origin, :product, :quantity, 'done', :to_location, :unit_price, FALSE, :uom, NOW()
                )
            """),
            {
                "company": company_id_for_move,
                "cost_price": None,
                "from_location": 1,  # Default warehouse location
                "internal_quantity": new_number,
                "origin": 'add_stock',
                "product": product_id,
                "quantity": change,
                "to_location": 2,  # Different warehouse location
                "uom": 1,  # Default unit of measure
                "unit_price": None
            }
        )
        db.commit()
        return {"message": "Stock updated", "product_id": product_id, "new_stock": new_number}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error: " + str(e))

@router.get("/by_code/{code}", summary="Fetch Products by Product Code")
async def fetch_products_by_code(code: str, db: Session = Depends(get_db)):
    try:
        rows = db.execute(text('''
            SELECT
                pp.id as product_id,
                pt.name,
                pt.code,
                pt.type,
                pp.description,
                plp.list_price as selling_price,
                pcp.cost_price as buying_price,
                party.name as supplier_company,
                pc.name as category_name
            FROM public.product_template pt
            JOIN public.product_product pp ON pp.template = pt.id
            LEFT JOIN public.product_list_price plp ON plp.template = pt.id
            LEFT JOIN public.product_cost_price pcp ON pcp.product = pp.id
            LEFT JOIN public.purchase_product_supplier pps ON pps.product = pp.id
            LEFT JOIN public.company_company cc ON cc.id = pps.company
            LEFT JOIN public.party_party party ON party.id = cc.party
            LEFT JOIN public.\"product_template-product_category\" ptc ON ptc.template = pt.id
            LEFT JOIN public.product_category pc ON pc.id = ptc.category
            WHERE pt.code = :code OR pp.code = :code
        '''), {"code": code}).fetchall()
        return [dict(row._mapping) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error: " + str(e))

@router.get("/by_type/{product_type}", summary="Fetch Products by Product Type")
async def fetch_products_by_type(product_type: str, db: Session = Depends(get_db)):
    try:
        rows = db.execute(text('''
            SELECT
                pp.id as product_id,
                pt.name,
                pt.code,
                pt.type,
                pp.description,
                plp.list_price as selling_price,
                pcp.cost_price as buying_price,
                party.name as supplier_company,
                pc.name as category_name
            FROM public.product_template pt
            JOIN public.product_product pp ON pp.template = pt.id
            LEFT JOIN public.product_list_price plp ON plp.template = pt.id
            LEFT JOIN public.product_cost_price pcp ON pcp.product = pp.id
            LEFT JOIN public.purchase_product_supplier pps ON pps.product = pp.id
            LEFT JOIN public.company_company cc ON cc.id = pps.company
            LEFT JOIN public.party_party party ON party.id = cc.party
            LEFT JOIN public.\"product_template-product_category\" ptc ON ptc.template = pt.id
            LEFT JOIN public.product_category pc ON pc.id = ptc.category
            WHERE pt.type = :product_type
        '''), {"product_type": product_type}).fetchall()
        return [dict(row._mapping) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error: " + str(e))

@router.get("/by_category/{category_id}", summary="Fetch Products by Category")
async def fetch_products_by_category(category_id: int, db: Session = Depends(get_db)):
    try:
        rows = db.execute(text('''
            SELECT
                pp.id as product_id,
                pt.name,
                pt.code,
                pt.type,
                pp.description,
                plp.list_price as selling_price,
                pcp.cost_price as buying_price,
                party.name as supplier_company,
                pc.name as category_name
            FROM public.product_template pt
            JOIN public.product_product pp ON pp.template = pt.id
            LEFT JOIN public.product_list_price plp ON plp.template = pt.id
            LEFT JOIN public.product_cost_price pcp ON pcp.product = pp.id
            LEFT JOIN public.purchase_product_supplier pps ON pps.product = pp.id
            LEFT JOIN public.company_company cc ON cc.id = pps.company
            LEFT JOIN public.party_party party ON party.id = cc.party
            LEFT JOIN public."product_template-product_category" ptc ON ptc.template = pt.id
            LEFT JOIN public.product_category pc ON pc.id = ptc.category
            WHERE ptc.category = :category_id
        '''), {"category_id": category_id}).fetchall()
        return [dict(row._mapping) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error: " + str(e))

@router.get("/{product_id}/stock_history", summary="Fetch Stock History for Product")
async def fetch_stock_history(product_id: int, db: Session = Depends(get_db)):
    try:
        # Get current stock
        current_stock = db.execute(
            text("""
                SELECT 
                    CAST(sl.number AS FLOAT) as current_quantity,
                    CASE 
                        WHEN CAST(sl.number AS FLOAT) = 0 THEN 'Stockout'
                        WHEN CAST(sl.number AS FLOAT) > 0 THEN 'In Stock'
                        ELSE 'Unknown'
                    END as stock_status
                FROM public.stock_lot sl
                WHERE sl.product = :product_id
            """),
            {"product_id": product_id}
        ).fetchone()

        # Get stock movement history
        rows = db.execute(text('''
            SELECT
                id,
                company,
                cost_price,
                create_date,
                effective_date,
                from_location,
                internal_quantity,
                origin,
                product,
                quantity,
                state,
                to_location,
                unit_price,
                unit_price_updated,
                write_date,
                CASE 
                    WHEN origin = 'add_product' THEN 'Product Addition'
                    WHEN origin = 'add_stock' THEN 'Stock Addition'
                    WHEN origin = 'set_stock' THEN 'Stock Update'
                    ELSE origin
                END as movement_type,
                CASE 
                    WHEN quantity > 0 THEN 'Incoming'
                    WHEN quantity < 0 THEN 'Outgoing'
                    ELSE 'No Change'
                END as movement_direction
            FROM public.stock_move
            WHERE product = :product_id
            ORDER BY create_date DESC
        '''), {"product_id": product_id}).fetchall()

        # Format the response
        history = [dict(row._mapping) for row in rows]
        
        # Add readable location names
        for entry in history:
            # Get from_location name
            from_loc = db.execute(
                text("SELECT name FROM public.stock_location WHERE id = :id"),
                {"id": entry['from_location']}
            ).fetchone()
            entry['from_location_name'] = from_loc.name if from_loc else 'Unknown'

            # Get to_location name
            to_loc = db.execute(
                text("SELECT name FROM public.stock_location WHERE id = :id"),
                {"id": entry['to_location']}
            ).fetchone()
            entry['to_location_name'] = to_loc.name if to_loc else 'Unknown'

        return {
            "current_stock": {
                "quantity": current_stock.current_quantity if current_stock else 0,
                "status": current_stock.stock_status if current_stock else "Unknown"
            },
            "history": history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error: " + str(e))