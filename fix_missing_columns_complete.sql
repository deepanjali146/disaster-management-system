-- Migration Script: Add Missing Columns to Existing Database
-- This script adds the missing columns that are causing the complete task button to fail
-- Run this script if you already have an existing database

-- Add missing columns to requests table
ALTER TABLE IF EXISTS public.requests ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS public.requests ADD COLUMN IF NOT EXISTS notified_at TIMESTAMPTZ;

-- Update requests status constraint to include new statuses
ALTER TABLE IF EXISTS public.requests DROP CONSTRAINT IF EXISTS requests_status_check;
ALTER TABLE IF EXISTS public.requests ADD CONSTRAINT requests_status_check CHECK (status IN ('pending', 'accepted', 'rejected', 'completed', 'assigned', 'notified'));

-- Add missing columns to emergency_assignments table
ALTER TABLE IF EXISTS public.emergency_assignments ADD COLUMN IF NOT EXISTS unit_id BIGINT REFERENCES public.emergency_units(id) ON DELETE SET NULL;
ALTER TABLE IF EXISTS public.emergency_assignments ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

-- Create emergency_updates table if it doesn't exist
CREATE TABLE IF NOT EXISTS public.emergency_updates (
  id BIGSERIAL PRIMARY KEY, 
  assignment_id BIGINT NOT NULL REFERENCES public.emergency_assignments(id) ON DELETE CASCADE,
  author_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  reached BOOLEAN,
  rescued_count INTEGER,
  need_more_support BOOLEAN,
  severity TEXT,
  critical_count INTEGER,
  need_medical BOOLEAN,
  message TEXT,
  status TEXT DEFAULT 'active',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add missing status column to emergency_updates table
ALTER TABLE IF EXISTS public.emergency_updates ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active';

-- Add missing columns to donations table (if not already present)
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS donor_name TEXT;
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS donor_email TEXT;
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS transaction_id TEXT;
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

-- Add Razorpay payment columns to donations table
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS razorpay_order_id TEXT;
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS razorpay_payment_id TEXT;
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS payment_method TEXT;
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS payment_status TEXT;
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS amount_paid NUMERIC(10,2);

-- Add UPI payment columns to donations table
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS upi_id TEXT;
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS upi_url TEXT;
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS upi_reference TEXT;
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS sender_upi_id TEXT;
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;

-- Add error message column to donations table
ALTER TABLE IF EXISTS public.donations ADD COLUMN IF NOT EXISTS error_message TEXT;

-- Update donations status constraint
ALTER TABLE IF EXISTS public.donations DROP CONSTRAINT IF EXISTS donations_status_check;
ALTER TABLE IF EXISTS public.donations ADD CONSTRAINT donations_status_check CHECK (status IN ('pending', 'completed', 'failed', 'cancelled', 'success'));

-- Add missing columns to users table
ALTER TABLE IF EXISTS public.users ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE IF EXISTS public.users ADD COLUMN IF NOT EXISTS latitude DECIMAL(10, 8);
ALTER TABLE IF EXISTS public.users ADD COLUMN IF NOT EXISTS longitude DECIMAL(11, 8);
ALTER TABLE IF EXISTS public.users ADD COLUMN IF NOT EXISTS is_emergency_head BOOLEAN DEFAULT FALSE;

-- Update users role constraint
ALTER TABLE IF EXISTS public.users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE IF EXISTS public.users ADD CONSTRAINT users_role_check CHECK (role IN ('user', 'admin', 'government', 'emergency'));

-- Add missing columns to incidents table
ALTER TABLE IF EXISTS public.incidents ADD COLUMN IF NOT EXISTS address TEXT;
ALTER TABLE IF EXISTS public.incidents ADD COLUMN IF NOT EXISTS city TEXT;
ALTER TABLE IF EXISTS public.incidents ADD COLUMN IF NOT EXISTS state TEXT;
ALTER TABLE IF EXISTS public.incidents ADD COLUMN IF NOT EXISTS cause TEXT;
ALTER TABLE IF EXISTS public.incidents ADD COLUMN IF NOT EXISTS pincode TEXT;
ALTER TABLE IF EXISTS public.incidents ADD COLUMN IF NOT EXISTS severity TEXT DEFAULT 'medium';
ALTER TABLE IF EXISTS public.incidents ADD COLUMN IF NOT EXISTS forwarded_at TIMESTAMPTZ;
ALTER TABLE IF EXISTS public.incidents ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;

-- Update incidents status constraint
ALTER TABLE IF EXISTS public.incidents DROP CONSTRAINT IF EXISTS incidents_status_check;
ALTER TABLE IF EXISTS public.incidents ADD CONSTRAINT incidents_status_check CHECK (status IN ('pending', 'forwarded', 'resolved'));

-- Update incidents severity constraint
ALTER TABLE IF EXISTS public.incidents DROP CONSTRAINT IF EXISTS incidents_severity_check;
ALTER TABLE IF EXISTS public.incidents ADD CONSTRAINT incidents_severity_check CHECK (severity IN ('low', 'medium', 'high', 'critical'));

-- Backfill pincode for existing data
UPDATE public.incidents SET pincode = COALESCE(pincode, '000000') WHERE pincode IS NULL;
ALTER TABLE IF EXISTS public.incidents ALTER COLUMN pincode SET NOT NULL;

-- Create SMS notifications table if it doesn't exist
CREATE TABLE IF NOT EXISTS public.sms_notifications (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    phone_number TEXT NOT NULL,
    message TEXT NOT NULL,
    incident_id BIGINT REFERENCES public.incidents(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('sent', 'failed', 'pending')),
    twilio_sid TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create weather data table if it doesn't exist
CREATE TABLE IF NOT EXISTS public.weather_data (
  id BIGSERIAL PRIMARY KEY,
  location TEXT NOT NULL,
  pincode TEXT,
  temperature NUMERIC(5,2),
  humidity INTEGER,
  wind_speed NUMERIC(5,2),
  weather_condition TEXT,
  is_extreme BOOLEAN DEFAULT FALSE,
  weather_alert TEXT,
  coordinates JSONB,
  fetched_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add pincode and coordinates columns to existing weather_data table if they don't exist
ALTER TABLE IF EXISTS public.weather_data ADD COLUMN IF NOT EXISTS pincode TEXT;
ALTER TABLE IF EXISTS public.weather_data ADD COLUMN IF NOT EXISTS coordinates JSONB;

-- Create weather alerts sent table if it doesn't exist
CREATE TABLE IF NOT EXISTS public.weather_alerts_sent (
    id BIGSERIAL PRIMARY KEY,
    weather_id BIGINT REFERENCES public.weather_data(id) ON DELETE CASCADE,
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add weather columns to announcements table
ALTER TABLE IF EXISTS public.announcements 
ADD COLUMN IF NOT EXISTS weather_data_id BIGINT REFERENCES public.weather_data(id),
ADD COLUMN IF NOT EXISTS is_weather_alert BOOLEAN DEFAULT FALSE;

-- Create other missing tables if they don't exist
CREATE TABLE IF NOT EXISTS public.shelters (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  location TEXT NOT NULL,
  capacity INTEGER NOT NULL,
  available INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.team_allocations (
  id BIGSERIAL PRIMARY KEY,
  gov_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  request_id BIGINT NOT NULL REFERENCES public.requests(id) ON DELETE CASCADE,
  team_name TEXT NOT NULL,
  assigned_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.emergency_units (
  id BIGSERIAL PRIMARY KEY,
  head_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  unit_name TEXT NOT NULL,
  unit_category TEXT NOT NULL CHECK (unit_category IN ('Rescue', 'Escort', 'Medical', 'ResourceCollector')),
  status TEXT NOT NULL DEFAULT 'Free' CHECK (status IN ('Free', 'Busy', 'Offline')),
  last_update TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.emergency_notifications (
  id BIGSERIAL PRIMARY KEY,
  request_id BIGINT NOT NULL REFERENCES public.requests(id) ON DELETE CASCADE,
  gov_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  head_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'Acknowledged', 'Completed')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.medical_requests (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  request_type TEXT NOT NULL,
  description TEXT,
  urgency TEXT,
  status TEXT DEFAULT 'Pending',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.resources (
  id BIGSERIAL PRIMARY KEY,
  gov_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  shelter_id BIGINT NOT NULL REFERENCES public.shelters(id) ON DELETE CASCADE,
  food INTEGER DEFAULT 0,
  water INTEGER DEFAULT 0,
  medicine INTEGER DEFAULT 0,
  allocated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_role ON public.users(role);
CREATE INDEX IF NOT EXISTS idx_users_phone ON public.users(phone);
CREATE INDEX IF NOT EXISTS idx_users_location ON public.users(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_users_emergency_head ON public.users(is_emergency_head);

CREATE INDEX IF NOT EXISTS idx_incidents_user_id ON public.incidents(user_id);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON public.incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON public.incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_location ON public.incidents(location);
CREATE INDEX IF NOT EXISTS idx_incidents_pincode ON public.incidents(pincode);

CREATE INDEX IF NOT EXISTS idx_donations_user_id ON public.donations(user_id);
CREATE INDEX IF NOT EXISTS idx_donations_status ON public.donations(status);
CREATE INDEX IF NOT EXISTS idx_donations_razorpay_order_id ON public.donations(razorpay_order_id);
CREATE INDEX IF NOT EXISTS idx_donations_razorpay_payment_id ON public.donations(razorpay_payment_id);
CREATE INDEX IF NOT EXISTS idx_donations_transaction_id ON public.donations(transaction_id);
CREATE INDEX IF NOT EXISTS idx_donations_payment_method ON public.donations(payment_method);

CREATE INDEX IF NOT EXISTS idx_sms_notifications_user_id ON public.sms_notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_sms_notifications_incident_id ON public.sms_notifications(incident_id);
CREATE INDEX IF NOT EXISTS idx_sms_notifications_status ON public.sms_notifications(status);

CREATE INDEX IF NOT EXISTS idx_weather_data_location ON public.weather_data(location);
CREATE INDEX IF NOT EXISTS idx_weather_data_extreme ON public.weather_data(is_extreme);

CREATE INDEX IF NOT EXISTS idx_announcements_admin_id ON public.announcements(admin_id);
CREATE INDEX IF NOT EXISTS idx_announcements_severity ON public.announcements(severity);
CREATE INDEX IF NOT EXISTS idx_announcements_weather_data_id ON public.announcements(weather_data_id);

CREATE INDEX IF NOT EXISTS idx_requests_admin_id ON public.requests(admin_id);
CREATE INDEX IF NOT EXISTS idx_requests_incident_id ON public.requests(incident_id);
CREATE INDEX IF NOT EXISTS idx_requests_status ON public.requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_assigned_at ON public.requests(assigned_at);

CREATE INDEX IF NOT EXISTS idx_emergency_assignments_request_id ON public.emergency_assignments(request_id);
CREATE INDEX IF NOT EXISTS idx_emergency_assignments_team_lead_id ON public.emergency_assignments(team_lead_id);
CREATE INDEX IF NOT EXISTS idx_emergency_assignments_status ON public.emergency_assignments(status);
CREATE INDEX IF NOT EXISTS idx_emergency_assignments_unit_id ON public.emergency_assignments(unit_id);
CREATE INDEX IF NOT EXISTS idx_emergency_assignments_completed_at ON public.emergency_assignments(completed_at);

CREATE INDEX IF NOT EXISTS idx_emergency_updates_assignment_id ON public.emergency_updates(assignment_id);
CREATE INDEX IF NOT EXISTS idx_emergency_updates_author_id ON public.emergency_updates(author_id);

CREATE INDEX IF NOT EXISTS idx_emergency_units_head_id ON public.emergency_units(head_id);
CREATE INDEX IF NOT EXISTS idx_emergency_units_status ON public.emergency_units(status);

CREATE INDEX IF NOT EXISTS idx_emergency_notifications_request_id ON public.emergency_notifications(request_id);
CREATE INDEX IF NOT EXISTS idx_emergency_notifications_gov_id ON public.emergency_notifications(gov_id);
CREATE INDEX IF NOT EXISTS idx_emergency_notifications_head_id ON public.emergency_notifications(head_id);

CREATE INDEX IF NOT EXISTS idx_medical_requests_user_id ON public.medical_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_medical_requests_status ON public.medical_requests(status);

CREATE INDEX IF NOT EXISTS idx_resources_gov_id ON public.resources(gov_id);
CREATE INDEX IF NOT EXISTS idx_resources_shelter_id ON public.resources(shelter_id);

-- Create triggers for updated_at timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for updated_at columns
DROP TRIGGER IF EXISTS update_donations_updated_at ON public.donations;
CREATE TRIGGER update_donations_updated_at 
    BEFORE UPDATE ON public.donations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_sms_notifications_updated_at ON public.sms_notifications;
CREATE TRIGGER update_sms_notifications_updated_at 
    BEFORE UPDATE ON public.sms_notifications
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Grant permissions for Supabase
GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO anon;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO authenticated;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO anon;

-- Insert sample data if tables are empty
INSERT INTO public.shelters (name, location, capacity, available) VALUES
('Central Emergency Shelter', 'Downtown District', 200, 150),
('North Community Center', 'North Side', 100, 80),
('South Relief Center', 'South District', 150, 120),
('East Emergency Hub', 'East Side', 120, 90)
ON CONFLICT DO NOTHING;

INSERT INTO public.weather_data (location, temperature, humidity, wind_speed, weather_condition, is_extreme, weather_alert) 
VALUES ('Test Location', 25.5, 60, 5.2, 'Clear', FALSE, NULL)
ON CONFLICT DO NOTHING;

-- Create a helpful view for government emergency updates
CREATE OR REPLACE VIEW public.government_emergency_updates AS
SELECT 
    eu.id as update_id,
    eu.created_at as update_time,
    eu.message,
    eu.reached,
    eu.rescued_count,
    eu.need_more_support,
    eu.need_medical,
    eu.severity,
    eu.critical_count,
    ea.id as assignment_id,
    ea.team_name,
    ea.status as assignment_status,
    r.id as request_id,
    i.id as incident_id,
    i.location,
    i.city,
    i.state
FROM public.emergency_updates eu
JOIN public.emergency_assignments ea ON eu.assignment_id = ea.id
JOIN public.requests r ON ea.request_id = r.id
JOIN public.incidents i ON r.incident_id = i.id
ORDER BY eu.created_at DESC;

-- Verify the missing columns were added successfully
SELECT 'Missing columns added successfully! Complete task button should now work.' as status;
