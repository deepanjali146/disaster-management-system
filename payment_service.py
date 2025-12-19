"""
Razorpay Payment Service for Donations
"""
import razorpay
import qrcode
import io
import base64
import time
from config import Config
from supabase import create_client, Client
import logging
import json

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        self.client = None
        self.supabase = None
        
        # Initialize Razorpay client
        if Config.is_razorpay_configured():
            self.client = razorpay.Client(auth=(Config.RAZORPAY_KEY_ID, Config.RAZORPAY_KEY_SECRET))
            logger.info("Razorpay payment service initialized")
        else:
            logger.warning("Razorpay not configured. Payment features will be disabled.")
        
        # Initialize Supabase client
        if Config.is_supabase_configured():
            self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
            logger.info("Supabase client initialized for payment logging")
        else:
            logger.warning("Supabase not configured. Payment logs will not be saved.")
    
    def create_donation_order(self, amount, user_id, donor_name, donor_email):
        """
        Create a Razorpay order for donation
        """
        if not self.client:
            logger.error("Razorpay client not initialized")
            return None
        
        try:
            # Convert amount to paise (Razorpay expects amount in smallest currency unit)
            amount_paise = int(amount * 100)
            
            # Create order
            order_data = {
                'amount': amount_paise,
                'currency': 'INR',
                'receipt': f'donation_{user_id}_{int(time.time())}',
                'notes': {
                    'donor_name': donor_name,
                    'donor_email': donor_email,
                    'user_id': user_id
                }
            }
            
            order = self.client.order.create(data=order_data)
            
            # Log the order
            self._log_payment_order(order, user_id, amount, donor_name, donor_email)
            
            logger.info(f"Payment order created: {order['id']}")
            return order
            
        except Exception as e:
            logger.error(f"Error creating payment order: {str(e)}")
            return None
    
    def verify_payment(self, razorpay_order_id, razorpay_payment_id, razorpay_signature):
        """
        Verify Razorpay payment signature
        """
        if not self.client:
            logger.error("Razorpay client not initialized")
            return False
        
        try:
            # Create verification data
            verification_data = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            }
            
            # Verify signature
            self.client.utility.verify_payment_signature(verification_data)
            
            # Get payment details
            payment = self.client.payment.fetch(razorpay_payment_id)
            
            # Update payment status in database
            self._update_payment_status(razorpay_order_id, 'success', payment)
            
            logger.info(f"Payment verified successfully: {razorpay_payment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Payment verification failed: {str(e)}")
            self._update_payment_status(razorpay_order_id, 'failed', {'error': str(e)})
            return False
    
    def create_donation_qr_code(self, amount, user_id, donor_name, donor_email):
        """
        Create QR code for donation payment
        """
        try:
            # Create order first
            order = self.create_donation_order(amount, user_id, donor_name, donor_email)
            if not order:
                return None
            
            # Create payment URL
            payment_url = f"https://rzp.io/l/{order['id']}"
            
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(payment_url)
            qr.make(fit=True)
            
            # Create QR code image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64 for web display
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_str = base64.b64encode(buffer.getvalue()).decode()
            
            return {
                'order_id': order['id'],
                'amount': amount,
                'qr_code': img_str,
                'payment_url': payment_url,
                'razorpay_key_id': Config.RAZORPAY_KEY_ID
            }
            
        except Exception as e:
            logger.error(f"Error creating donation QR code: {str(e)}")
            return None
    
    def _log_payment_order(self, order, user_id, amount, donor_name, donor_email):
        """
        Log payment order to database with all required details
        """
        if not self.supabase:
            return
        
        try:
            order_data = {
                'user_id': user_id,
                'amount': amount,
                'method': 'razorpay',
                'donor_name': donor_name,
                'donor_email': donor_email,
                'status': 'pending',
                'razorpay_order_id': order['id'],
                'payment_method': 'razorpay',
                'currency': order.get('currency', 'INR'),
                'receipt': order.get('receipt'),
                'created_at': 'now()',
                'updated_at': 'now()'
            }
            
            result = self.supabase.table('donations').insert(order_data).execute()
            if result and result.data:
                logger.info(f"Payment order logged: {result.data[0]['id']}")
            else:
                logger.error("Failed to log payment order")
                
        except Exception as e:
            logger.error(f"Error logging payment order: {str(e)}")
    
    def _update_payment_status(self, order_id, status, payment_data=None):
        """
        Update payment status in database
        """
        if not self.supabase:
            return
        
        try:
            update_data = {
                'status': status,
                'updated_at': 'now()'
            }
            
            if payment_data and status == 'success':
                update_data.update({
                    'razorpay_payment_id': payment_data.get('id'),
                    'payment_method': payment_data.get('method'),
                    'payment_status': payment_data.get('status'),
                    'amount_paid': payment_data.get('amount') / 100 if payment_data.get('amount') else None
                })
            elif payment_data and status == 'failed':
                update_data['error_message'] = payment_data.get('error', 'Payment failed')
            
            result = self.supabase.table('donations').update(update_data).eq('razorpay_order_id', order_id).execute()
            
            if result and result.data:
                logger.info(f"Payment status updated: {order_id} -> {status}")
            else:
                logger.error(f"Failed to update payment status for order: {order_id}")
                
        except Exception as e:
            logger.error(f"Error updating payment status: {str(e)}")
    
    def get_donation_history(self, user_id=None):
        """
        Get donation history
        """
        if not self.supabase:
            return []
        
        try:
            query = self.supabase.table('donations').select('*')
            
            if user_id:
                query = query.eq('user_id', user_id)
            
            result = query.order('created_at', desc=True).execute()
            
            if result and result.data:
                return result.data
            return []
            
        except Exception as e:
            logger.error(f"Error getting donation history: {str(e)}")
            return []
    
    def get_donation_stats(self):
        """
        Get donation statistics
        """
        if not self.supabase:
            return {}
        
        try:
            # Get total donations
            total_result = self.supabase.table('donations').select('amount').eq('status', 'success').execute()
            total_amount = sum(donation['amount'] for donation in total_result.data) if total_result.data else 0
            
            # Get total count
            count_result = self.supabase.table('donations').select('id', count='exact').eq('status', 'success').execute()
            total_count = count_result.count if count_result.count else 0
            
            # Get recent donations
            recent_result = self.supabase.table('donations').select('*').eq('status', 'success').order('created_at', desc=True).limit(5).execute()
            recent_donations = recent_result.data if recent_result.data else []
            
            return {
                'total_amount': total_amount,
                'total_count': total_count,
                'recent_donations': recent_donations
            }
            
        except Exception as e:
            logger.error(f"Error getting donation stats: {str(e)}")
            return {}

# Global payment service instance
payment_service = PaymentService()
