# 🌪️ Disaster Management System - ResQchain

A comprehensive disaster management platform with real-time incident reporting, SMS notifications, payment integration, and multi-role dashboards.

## ✨ Features

### 🚨 Core Features
- **Real-time Incident Reporting** - Users can report incidents with location, photos, and descriptions
- **Multi-role Dashboards** - Separate interfaces for Users, Admins, Government, and Emergency Teams
- **Weather Monitoring** - Real-time weather data and extreme weather alerts
- **Shelter Management** - Find and manage nearby emergency shelters
- **Medical Assistance** - Request and track medical help

### 📱 New Features
- **SMS Notifications** - Automatic SMS alerts to nearby users when incidents are forwarded
- **Razorpay Integration** - Secure payment processing with QR code donations
- **Async Task Processing** - Scalable background processing with Celery and Redis
- **Enhanced UI** - Modern, responsive design with consistent theming
- **Real-time Updates** - Live notifications and status updates

## 🛠️ Technology Stack

- **Backend**: Flask, Python 3.8+
- **Database**: Supabase (PostgreSQL)
- **SMS**: Twilio
- **Payments**: Razorpay
- **Task Queue**: Celery + Redis
- **Frontend**: Bootstrap 5, HTML5, CSS3, JavaScript
- **Maps**: OpenStreetMap (via Overpy)
- **Weather**: wttr.in API

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Redis server (optional, for async tasks)
- Supabase account
- TextBelt account (free SMS) or Twilio account (optional)
- Razorpay account (for payments)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Disaster1
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp ENV_TEMPLATE.txt .env
   # Edit .env with your actual API keys and credentials
   ```

5. **Set up database**
   ```bash
   # Run the database schema updates
   psql -h your-supabase-host -U postgres -d postgres -f database_schema_updates.sql
   ```

6. **Add test phone numbers (optional)**
   ```bash
   python add_phone_numbers.py
   ```

7. **Test SMS functionality (optional)**
   ```bash
   python test_sms.py
   ```

8. **Start Redis server (optional, for async tasks)**
   ```bash
   # On Windows: Download and run Redis
   # On macOS: brew install redis && brew services start redis
   # On Linux: sudo apt-get install redis-server && sudo systemctl start redis
   ```

9. **Run the application**
   ```bash
   python app.py
   # OR for full async functionality:
   python run_app.py
   ```

   Or run components separately:
   ```bash
   # Terminal 1: Start Flask app
   python app.py
   
   # Terminal 2: Start Celery worker
   celery -A celery_config worker --loglevel=info
   
   # Terminal 3: Start Celery beat (for scheduled tasks)
   celery -A celery_config beat --loglevel=info
   ```

## 🔧 Configuration

### Environment Variables

Create a `.env` file with the following variables:

```env
# Flask Configuration
FLASK_SECRET_KEY=your-secret-key-here

# Supabase Configuration
SUPABASE_URL=your-supabase-url
SUPABASE_KEY=your-supabase-key

# Twilio SMS Configuration
TWILIO_ACCOUNT_SID=your-twilio-account-sid
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_PHONE_NUMBER=your-twilio-phone-number

# Razorpay Payment Configuration
RAZORPAY_KEY_ID=your-razorpay-key-id
RAZORPAY_KEY_SECRET=your-razorpay-key-secret

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Application Configuration
APP_BASE_URL=http://localhost:5000
```

### API Keys Setup

1. **Supabase**: Get your URL and key from [supabase.com](https://supabase.com)
2. **SMS Service**: 
   - **Free Option**: Get API key from [textbelt.com](https://textbelt.com) (1 free SMS per day)
   - **Paid Option**: Sign up at [twilio.com](https://twilio.com) for unlimited SMS
3. **Razorpay**: Sign up at [razorpay.com](https://razorpay.com) and get your API keys
4. **Redis**: Install locally or use a cloud service like Redis Cloud (optional for basic functionality)

## 📱 Usage

### User Roles

1. **Regular Users**
   - Report incidents
   - View announcements
   - Find nearby shelters
   - Request medical assistance
   - Make donations

2. **Admins**
   - Manage incidents
   - Forward incidents to government
   - Create announcements
   - View analytics
   - Send SMS notifications

3. **Government Officials**
   - Review forwarded incidents
   - Allocate emergency teams
   - Manage resources
   - Coordinate responses

4. **Emergency Teams**
   - Manage emergency units
   - Update response status
   - Coordinate with government
   - Track resources

### Key Features

#### SMS Notifications
- Automatic SMS alerts sent to nearby users when incidents are forwarded
- Weather alerts for extreme conditions
- Configurable notification radius
- Delivery status tracking

#### Payment Integration
- Secure donations via Razorpay
- QR code generation for easy payments
- Payment verification and confirmation
- Donation history and statistics

#### Real-time Updates
- Live incident status updates
- Weather monitoring
- Emergency team coordination
- Resource tracking

## 🗄️ Database Schema

The system uses the following main tables:

- `users` - User accounts and profiles
- `incidents` - Incident reports
- `donations` - Donation records
- `sms_notifications` - SMS delivery logs
- `weather_data` - Weather information
- `announcements` - System announcements
- `shelters` - Emergency shelter information

## 🔒 Security Features

- Role-based access control
- Secure payment processing
- SMS verification
- Data encryption
- Input validation
- SQL injection prevention

## 📊 Monitoring and Analytics

- Real-time dashboard metrics
- SMS delivery tracking
- Payment success rates
- Incident response times
- User engagement statistics

## 🚀 Deployment

### Production Deployment

1. **Set up production environment**
   ```bash
   export FLASK_ENV=production
   export REDIS_URL=your-production-redis-url
   ```

2. **Configure production database**
   - Update Supabase connection settings
   - Run database migrations

3. **Set up Celery workers**
   ```bash
   celery -A celery_config worker --loglevel=info --concurrency=4
   ```

4. **Configure reverse proxy** (Nginx)
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

5. **Set up SSL certificate**
   ```bash
   certbot --nginx -d your-domain.com
   ```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Check the documentation
- Contact the development team

## 🔄 Changelog

### Version 2.0.0
- Added SMS notification system
- Integrated Razorpay payments
- Implemented async task processing
- Enhanced UI/UX design
- Added QR code donations
- Improved sidebar navigation
- Added comprehensive monitoring

### Version 1.0.0
- Initial release
- Basic incident reporting
- Multi-role dashboards
- Weather monitoring
- Shelter management

## 🎯 Roadmap

- [ ] Mobile app development
- [ ] Advanced analytics dashboard
- [ ] Integration with more payment gateways
- [ ] Multi-language support
- [ ] Advanced mapping features
- [ ] IoT device integration
- [ ] Machine learning for incident prediction

---

**Built with ❤️ for disaster management and emergency response**
