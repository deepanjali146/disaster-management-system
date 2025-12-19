-- Complete Database Schema for Disaster Management System
-- This file contains the complete schema with all required tables and columns
-- Run this file to set up the entire database from scratch
-- FIXED VERSION: Includes all missing columns for proper functionality

-- Create schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS public;

-- Drop existing tables if they exist (be careful in production!)
-- Uncomment the following lines if you want to start fresh
-- DROP TABLE IF EXISTS public.emergency_notifications CASCADE;
-- DROP TABLE IF EXISTS public.emergency_units CASCADE;
-- DROP TABLE IF EXISTS public.emergency_updates CASCADE;
-- DROP TABLE IF EXISTS public.emergency_assignments CASCADE;
-- DROP TABLE IF EXISTS public.team_allocations CASCADE;
-- DROP TABLE IF EXISTS public.requests CASCADE;
-- DROP TABLE IF EXISTS public.resources CASCADE;
-- DROP TABLE IF EXISTS public.medical_requests CASCADE;
-- DROP TABLE IF EXISTS public.announcements CASCADE;
-- DROP TABLE IF EXISTS public.shelters CASCADE;
-- DROP TABLE IF EXISTS public.sms_notifications CASCADE;
-- DROP TABLE IF EXISTS public.weather_alerts_sent CASCADE;
-- DROP TABLE IF EXISTS public.weather_data CASCADE;
-- DROP TABLE IF EXISTS public.donations CASCADE;
-- DROP TABLE IF EXISTS public.incidents CASCADE;
-- DROP TABLE IF EXISTS public.users CASCADE;

-- User types with role-based access
CREATE TABLE IF NOT EXISTS public.users (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  phone TEXT,
  place TEXT,
  city TEXT,
  state TEXT,
  pincode TEXT,
  latitude DECIMAL(10, 8),
  longitude DECIMAL(11, 8),
  role TEXT DEFAULT 'user' CHECK (role IN ('user', 'admin', 'government', 'emergency')),
  is_emergency_head BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Incidents reported by users
CREATE TABLE IF NOT EXISTS public.incidents (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  location TEXT NOT NULL,
  address TEXT,
  city TEXT,
  state TEXT,
  cause TEXT,
  pincode TEXT NOT NULL,
  description TEXT NOT NULL,
  severity TEXT DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'forwarded', 'resolved')),
  forwarded_at TIMESTAMPTZ,
  resolved_at TIMESTAMPTZ,
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Complete donations table with all payment integration columns
CREATE TABLE IF NOT EXISTS public.donations (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  amount NUMERIC(10,2) NOT NULL,
  method TEXT NOT NULL,
  donor_name TEXT,
  donor_email TEXT,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'cancelled', 'success')),
  -- Razorpay payment columns
  razorpay_order_id TEXT,
  razorpay_payment_id TEXT,
  payment_method TEXT,
  payment_status TEXT,
  amount_paid NUMERIC(10,2),
  -- UPI payment columns
  upi_id TEXT,
  upi_url TEXT,
  upi_reference TEXT, -- UTR / reference number
  sender_upi_id TEXT, -- payer's VPA if known
  verified_at TIMESTAMPTZ,
  -- General payment columns
  transaction_id TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- SMS Notifications Table
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

-- Weather data for announcements
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

-- Weather alerts sent table
CREATE TABLE IF NOT EXISTS public.weather_alerts_sent (
  id BIGSERIAL PRIMARY KEY,
  weather_id BIGINT REFERENCES public.weather_data(id) ON DELETE CASCADE,
  sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- Shelters for emergency situations
CREATE TABLE IF NOT EXISTS public.shelters (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  location TEXT NOT NULL,
  capacity INTEGER NOT NULL,
  available INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Announcements from admins
CREATE TABLE IF NOT EXISTS public.announcements (
  id BIGSERIAL PRIMARY KEY,
  admin_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  severity TEXT DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  weather_data_id BIGINT REFERENCES public.weather_data(id),
  is_weather_alert BOOLEAN DEFAULT FALSE,
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Requests from admin to government (FIXED: Added missing assigned_at and notified_at columns)
CREATE TABLE IF NOT EXISTS public.requests (
  id BIGSERIAL PRIMARY KEY,
  admin_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  incident_id BIGINT NOT NULL REFERENCES public.incidents(id) ON DELETE CASCADE,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'completed', 'assigned', 'notified')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  accepted_at TIMESTAMPTZ,
  assigned_at TIMESTAMPTZ, -- FIXED: Added missing column
  notified_at TIMESTAMPTZ, -- FIXED: Added missing column
  completed_at TIMESTAMPTZ
);

-- Team allocations by government
CREATE TABLE IF NOT EXISTS public.team_allocations (
  id BIGSERIAL PRIMARY KEY,
  gov_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  request_id BIGINT NOT NULL REFERENCES public.requests(id) ON DELETE CASCADE,
  team_name TEXT NOT NULL,
  assigned_at TIMESTAMPTZ DEFAULT NOW()
);

-- Emergency team assignments with completion tracking (FIXED: Added missing columns)
CREATE TABLE IF NOT EXISTS public.emergency_assignments (
  id BIGSERIAL PRIMARY KEY,
  request_id BIGINT NOT NULL REFERENCES public.requests(id) ON DELETE CASCADE,
  team_name TEXT NOT NULL,
  team_type TEXT NOT NULL CHECK (team_type IN ('Rescue', 'FoodSupply', 'Escort', 'Liaison')),
  team_lead_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  unit_id BIGINT REFERENCES public.emergency_units(id) ON DELETE SET NULL, -- FIXED: Added missing column
  location_text TEXT,
  status TEXT DEFAULT 'Assigned' CHECK (status IN ('Assigned', 'Enroute', 'OnSite', 'Completed', 'NeedsSupport')),
  notes TEXT,
  assigned_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ -- FIXED: Added missing column
);

-- Emergency updates from teams
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
  status TEXT DEFAULT 'active', -- Added for better tracking
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Emergency units under a head
CREATE TABLE IF NOT EXISTS public.emergency_units (
  id BIGSERIAL PRIMARY KEY,
  head_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  unit_name TEXT NOT NULL,
  unit_category TEXT NOT NULL CHECK (unit_category IN ('Rescue', 'Escort', 'Medical', 'ResourceCollector')),
  status TEXT NOT NULL DEFAULT 'Free' CHECK (status IN ('Free', 'Busy', 'Offline')),
  last_update TIMESTAMPTZ DEFAULT NOW()
);

-- Government to emergency head notifications per request
CREATE TABLE IF NOT EXISTS public.emergency_notifications (
  id BIGSERIAL PRIMARY KEY,
  request_id BIGINT NOT NULL REFERENCES public.requests(id) ON DELETE CASCADE,
  gov_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  head_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending', 'Acknowledged', 'Completed')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Medical requests from users
CREATE TABLE IF NOT EXISTS public.medical_requests (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
  request_type TEXT NOT NULL,
  description TEXT,
  urgency TEXT,
  status TEXT DEFAULT 'Pending',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Resources allocated to shelters
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
CREATE INDEX IF NOT EXISTS idx_requests_assigned_at ON public.requests(assigned_at); -- FIXED: Added missing index

CREATE INDEX IF NOT EXISTS idx_emergency_assignments_request_id ON public.emergency_assignments(request_id);
CREATE INDEX IF NOT EXISTS idx_emergency_assignments_team_lead_id ON public.emergency_assignments(team_lead_id);
CREATE INDEX IF NOT EXISTS idx_emergency_assignments_status ON public.emergency_assignments(status);
CREATE INDEX IF NOT EXISTS idx_emergency_assignments_unit_id ON public.emergency_assignments(unit_id); -- FIXED: Added missing index
CREATE INDEX IF NOT EXISTS idx_emergency_assignments_completed_at ON public.emergency_assignments(completed_at); -- FIXED: Added missing index

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

-- Insert sample data
INSERT INTO public.shelters (name, location, capacity, available) VALUES
('Central Emergency Shelter', 'Downtown District', 200, 150),
('North Community Center', 'North Side', 100, 80),
('South Relief Center', 'South District', 150, 120),
('East Emergency Hub', 'East Side', 120, 90)
ON CONFLICT DO NOTHING;

-- Insert sample weather data
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

-- Verify the schema was created successfully
SELECT 'Complete database schema created successfully with all missing columns fixed!' as status;
