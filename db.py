import mysql.connector
from mysql.connector import Error
from contextlib import contextmanager

class Database:
    def __init__(self):
        self.config = {
            'host': 'localhost',
            'user': 'root',
            'password': 'password',  # Change this
            'database': 'invoice_hub',
            'autocommit': True
        }
    
    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = mysql.connector.connect(**self.config)
            yield conn
        except Error as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn and conn.is_connected():
                conn.close()
    
    def get_client_id(self, client_name):
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id FROM clients WHERE LOWER(name) = LOWER(%s)", (client_name,))
            result = cursor.fetchone()
            if result:
                return result['id']
            
            # Insert new client
            cursor.execute("INSERT INTO clients (name) VALUES (%s)", (client_name,))
            return cursor.lastrowid
    
    def get_item_id(self, item_name, gst_percentage):
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id FROM items WHERE LOWER(name) = LOWER(%s)", (item_name,))
            result = cursor.fetchone()
            if result:
                return result['id']
            
            # Insert new item
            cursor.execute("INSERT INTO items (name, gst_percentage) VALUES (%s, %s)", 
                         (item_name, gst_percentage))
            return cursor.lastrowid
    
    def create_invoice(self, client_name, items_data):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get or create client
            client_id = self.get_client_id(client_name)
            
            # Generate invoice number
            cursor.execute("SELECT COUNT(*) as count FROM invoices")
            count = cursor.fetchone()[0] + 1
            invoice_number = f"INV-{count:04d}"
            invoice_date = "2025-12-19"  # Current date
            
            subtotal = sum(item['item_total'] for item in items_data)
            total_gst = sum(item['gst_amount'] for item in items_data)
            grand_total = subtotal + total_gst
            
            # Insert invoice
            cursor.execute("""
                INSERT INTO invoices (invoice_number, client_id, invoice_date, subtotal, total_gst, grand_total)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (invoice_number, client_id, invoice_date, subtotal, total_gst, grand_total))
            
            invoice_id = cursor.lastrowid
            
            # Insert invoice items
            for item_data in items_data:
                item_id = self.get_item_id(item_data['name'], item_data['gst_percentage'])
                cursor.execute("""
                    INSERT INTO invoice_items (invoice_id, item_id, quantity, unit_price, gst_percentage, item_total)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (invoice_id, item_id, item_data['quantity'], item_data['unit_price'], 
                      item_data['gst_percentage'], item_data['item_total']))
            
            return {
                'id': invoice_id,
                'invoice_number': invoice_number,
                'client_id': client_id,
                'subtotal': float(subtotal),
                'total_gst': float(total_gst),
                'grand_total': float(grand_total)
            }
    
    def get_invoices(self):
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT i.*, c.name as client_name,
                       SUM(ii.item_total) as items_total
                FROM invoices i
                JOIN clients c ON i.client_id = c.id
                LEFT JOIN invoice_items ii ON i.id = ii.invoice_id
                GROUP BY i.id
                ORDER BY i.created_at DESC
                LIMIT 10
            """)
            return cursor.fetchall()
    
    def get_invoice(self, invoice_id):
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT i.*, c.name as client_name
                FROM invoices i
                JOIN clients c ON i.client_id = c.id
                WHERE i.id = %s
            """, (invoice_id,))
            invoice = cursor.fetchone()
            
            if invoice:
                cursor.execute("""
                    SELECT ii.*, i.name as item_name, i.gst_percentage
                    FROM invoice_items ii
                    JOIN items i ON ii.item_id = i.id
                    WHERE ii.invoice_id = %s
                """, (invoice_id,))
                invoice['items'] = cursor.fetchall()
            
            return invoice
    
    def get_clients(self):
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, name FROM clients ORDER BY name")
            return cursor.fetchall()
    
    def get_items(self):
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, name, gst_percentage FROM items ORDER BY name")
            return cursor.fetchall()
    
    def get_dashboard_stats(self):
        with self.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("SELECT COUNT(*) as total_invoices FROM invoices")
            total_invoices = cursor.fetchone()['total_invoices']
            
            cursor.execute("SELECT SUM(grand_total) as total_revenue FROM invoices")
            total_revenue = cursor.fetchone()['total_revenue'] or 0
            
            cursor.execute("""
                SELECT SUM(grand_total) as pending_amount 
                FROM invoices 
                WHERE status = 'pending'
            """)
            pending_amount = cursor.fetchone()['pending_amount'] or 0
            
            return {
                'total_invoices': total_invoices,
                'total_revenue': float(total_revenue),
                'pending_amount': float(pending_amount)
            }
