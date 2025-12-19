# 📱 SMS Setup Guide

This guide explains how to set up SMS notifications for the Disaster Management System.

## 🆓 Free SMS Setup (Recommended for Testing)

### Option 1: TextBelt (Free Tier)
1. Go to [textbelt.com](https://textbelt.com)
2. Sign up for a free account
3. Get your API key from the dashboard
4. Add to your `.env` file:
   ```env
   SMS_API_KEY=your_textbelt_api_key_here
   ```
5. **Limitations**: 1 free SMS per day

### Option 2: Mock SMS (Development Only)
- If no API key is provided, the system will use mock SMS
- Messages will be logged to console instead of being sent
- Perfect for development and testing

## 💰 Paid SMS Setup (Production)

### Twilio (Recommended for Production)
1. Sign up at [twilio.com](https://twilio.com)
2. Get your Account SID, Auth Token, and Phone Number
3. Add to your `.env` file:
   ```env
   TWILIO_ACCOUNT_SID=your_twilio_account_sid
   TWILIO_AUTH_TOKEN=your_twilio_auth_token
   TWILIO_PHONE_NUMBER=your_twilio_phone_number
   ```

## 🧪 Testing SMS Functionality

### 1. Add Test Phone Numbers
```bash
python add_phone_numbers.py
```
This script adds sample phone numbers and locations to existing users.

### 2. Test SMS Sending
```bash
python test_sms.py
```
This script tests the SMS functionality with sample data.

### 3. Test in Application
1. Sign up as a user
2. Add your phone number in the profile
3. Report an incident
4. As an admin, forward the incident
5. Check if SMS notifications are sent

## 📋 SMS Features

### Automatic Notifications
- **When**: Admin forwards an incident to government
- **Who**: All users within 10km radius of incident
- **What**: Incident type, location, description, and link

### Message Format
```
🚨 EMERGENCY ALERT 🚨

[Incident Type] reported in [Location]

Details: [Description]

View details: [Link]

Stay safe and follow local authorities' instructions.

- ResQchain Emergency System
```

### Database Logging
- All SMS attempts are logged in `sms_notifications` table
- Tracks delivery status, errors, and user information
- Useful for monitoring and debugging

## 🔧 Configuration

### Environment Variables
```env
# Free SMS API
SMS_API_KEY=your_textbelt_api_key

# OR Twilio (paid)
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_token
TWILIO_PHONE_NUMBER=your_twilio_phone

# App URL for SMS links
APP_BASE_URL=http://localhost:5000
```

### Database Schema
The system uses these tables for SMS functionality:
- `users` - Stores phone numbers and locations
- `sms_notifications` - Logs all SMS attempts
- `incidents` - Incident data for SMS content

## 🚨 Troubleshooting

### Common Issues

1. **"No nearby users found"**
   - Ensure users have phone numbers in database
   - Check if users have location data (latitude/longitude)
   - Run `add_phone_numbers.py` to add test data

2. **"SMS service not configured"**
   - Check if `SMS_API_KEY` is set in `.env` file
   - Verify Supabase connection

3. **"SMS sending failed"**
   - Check API key validity
   - Verify phone number format (include country code)
   - Check API rate limits

4. **"Mock SMS" messages in console**
   - This is normal when no API key is configured
   - Set up TextBelt or Twilio for real SMS sending

### Debug Mode
Enable debug logging by setting:
```env
FLASK_ENV=development
```

## 📊 Monitoring

### Check SMS Logs
Query the database to see SMS delivery status:
```sql
SELECT * FROM sms_notifications 
ORDER BY created_at DESC 
LIMIT 10;
```

### Success Rate
```sql
SELECT 
    status,
    COUNT(*) as count
FROM sms_notifications 
GROUP BY status;
```

## 🔒 Security Notes

- Never commit API keys to version control
- Use environment variables for all sensitive data
- Monitor SMS usage to avoid unexpected charges
- Implement rate limiting for production use

## 📞 Support

If you encounter issues:
1. Check the console logs for error messages
2. Verify your API key and configuration
3. Test with the provided test scripts
4. Check the database for SMS logs

---

**Happy SMS sending! 📱✨**
