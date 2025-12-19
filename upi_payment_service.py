"""
UPI Payment Service for Direct Money Transfer
"""
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

class UPIPaymentService:
    def __init__(self):
        self.supabase = None
        self.upi_id = "devsakhya2004@okicici"  # Your UPI ID
        
        # Initialize Supabase client
        if Config.is_supabase_configured():
            self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
            logger.info("Supabase client initialized for UPI payment logging")
        else:
            logger.warning("Supabase not configured. UPI payment logs will not be saved.")
    
    def create_upi_payment_qr(self, amount, user_id, donor_name, donor_email, purpose="Disaster Relief Donation"):
        """
        Create UPI payment QR code that sends money directly to your UPI ID
        """
        try:
            # Create UPI payment URL
            upi_url = self._create_upi_url(amount, purpose)
            
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(upi_url)
            qr.make(fit=True)
            
            # Create QR code image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64 for web display
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            img_str = base64.b64encode(buffer.getvalue()).decode()
            
            # Log the payment request and capture inserted donation id
            insert_id = self._log_payment_request(user_id, amount, donor_name, donor_email, upi_url)
            
            return {
                'upi_id': self.upi_id,
                'amount': amount,
                'qr_code': img_str,
                'upi_url': upi_url,
                'purpose': purpose,
                'donor_name': donor_name,
                'donor_email': donor_email,
                'transaction_id': insert_id
            }
            
        except Exception as e:
            logger.error(f"Error creating UPI payment QR: {str(e)}")
            return None
    
    def _create_upi_url(self, amount, purpose):
        """
        Create UPI payment URL that opens directly in UPI apps
        """
        # Format: upi://pay?pa=UPI_ID&pn=NAME&am=AMOUNT&cu=INR&tn=PURPOSE
        upi_url = f"upi://pay?pa={self.upi_id}&pn=Dev%20Sakhya&am={amount}&cu=INR&tn={purpose.replace(' ', '%20')}"
        return upi_url
    
    def verify_upi_payment(self, transaction_id, verification_code=None, sender_upi_id=None):
        """
        Mark a UPI payment as received. We treat the provided code as the
        UPI reference/UTR, and optionally store the sender's UPI ID.
        No strict format validation is enforced to keep manual reconciliation easy.
        """
        try:
            if not transaction_id:
                return False

            # Update payment status; store reference and sender UPI if provided
            self._update_payment_status(
                transaction_id=transaction_id,
                status='verified',
                upi_reference=verification_code,
                sender_upi_id=sender_upi_id
            )
            return True
            
        except Exception as e:
            logger.error(f"Error verifying UPI payment: {str(e)}")
            return False
    
    def _log_payment_request(self, user_id, amount, donor_name, donor_email, upi_url):
        """
        Log UPI payment request to database
        """
        if not self.supabase:
            return
        
        try:
            payment_data = {
                'user_id': user_id,
                'amount': amount,
                'donor_name': donor_name,
                'donor_email': donor_email,
                'upi_id': self.upi_id,
                'upi_url': upi_url,
                'status': 'pending',
                'payment_method': 'UPI',
                'created_at': 'now()'
            }
            
            result = self.supabase.table('donations').insert(payment_data).execute()
            if result and result.data:
                logger.info(f"UPI payment request logged: {result.data[0]['id']}")
                return result.data[0]['id']
            else:
                logger.error("Failed to log UPI payment request")
                return None
                
        except Exception as e:
            logger.error(f"Error logging UPI payment request: {str(e)}")
            return None
    
    def _update_payment_status(self, transaction_id, status, upi_reference=None, sender_upi_id=None):
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
            
            if upi_reference:
                update_data['upi_reference'] = upi_reference
            if sender_upi_id:
                update_data['sender_upi_id'] = sender_upi_id
            if status == 'verified':
                update_data['verified_at'] = 'now()'
            
            result = self.supabase.table('donations').update(update_data).eq('id', transaction_id).execute()
            
            if result and result.data:
                logger.info(f"Payment status updated: {transaction_id} -> {status}")
            else:
                logger.error(f"Failed to update payment status for transaction: {transaction_id}")
                
        except Exception as e:
            logger.error(f"Error updating payment status: {str(e)}")
    
    def get_donation_stats(self):
        """
        Get donation statistics
        """
        if not self.supabase:
            return {}
        
        try:
            # Get total donations
            total_result = self.supabase.table('donations').select('amount').eq('status', 'verified').execute()
            total_amount = sum(donation['amount'] for donation in total_result.data) if total_result.data else 0
            
            # Get total count
            count_result = self.supabase.table('donations').select('id', count='exact').eq('status', 'verified').execute()
            total_count = count_result.count if count_result.count else 0
            
            # Get recent donations
            recent_result = self.supabase.table('donations').select('*').eq('status', 'verified').order('created_at', desc=True).limit(5).execute()
            recent_donations = recent_result.data if recent_result.data else []
            
            return {
                'total_amount': total_amount,
                'total_count': total_count,
                'recent_donations': recent_donations
            }
            
        except Exception as e:
            logger.error(f"Error getting donation stats: {str(e)}")
            return {}
    
    def get_pending_donations(self):
        """
        Get pending donations for verification
        """
        if not self.supabase:
            return []
        
        try:
            result = self.supabase.table('donations').select('*').eq('status', 'pending').order('created_at', desc=True).execute()
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"Error getting pending donations: {str(e)}")
            return []

# Global UPI payment service instance
upi_payment_service = UPIPaymentService()
