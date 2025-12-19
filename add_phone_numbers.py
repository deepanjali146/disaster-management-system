#!/usr/bin/env python3
"""
Script to add phone numbers to existing users for SMS testing
"""
import os
import sys
from supabase import create_client, Client
from config import Config

def add_phone_numbers():
    """Add sample phone numbers to existing users"""
    
    if not Config.is_supabase_configured():
        print("❌ Supabase not configured. Please set SUPABASE_URL and SUPABASE_KEY in .env file")
        return
    
    try:
        supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        
        # Get all users without phone numbers
        result = supabase.table('users').select('id, name, email').is_('phone', 'null').execute()
        
        if not result or not result.data:
            print("✅ All users already have phone numbers")
            return
        
        print(f"Found {len(result.data)} users without phone numbers")
        
        # Sample phone numbers for testing (Indian format)
        sample_phones = [
            "+919876543210",
            "+919876543211", 
            "+919876543212",
            "+919876543213",
            "+919876543214",
            "+919876543215",
            "+919876543216",
            "+919876543217",
            "+919876543218",
            "+919876543219"
        ]
        
        # Sample coordinates for different Indian cities
        sample_locations = [
            {"lat": 28.6139, "lon": 77.2090},  # Delhi
            {"lat": 19.0760, "lon": 72.8777},  # Mumbai
            {"lat": 12.9716, "lon": 77.5946},  # Bangalore
            {"lat": 13.0827, "lon": 80.2707},  # Chennai
            {"lat": 22.5726, "lon": 88.3639},  # Kolkata
            {"lat": 18.5204, "lon": 73.8567},  # Pune
            {"lat": 26.9124, "lon": 75.7873},  # Jaipur
            {"lat": 17.3850, "lon": 78.4867},  # Hyderabad
            {"lat": 23.0225, "lon": 72.5714},  # Ahmedabad
            {"lat": 25.3176, "lon": 82.9739}   # Varanasi
        ]
        
        updated_count = 0
        
        for i, user in enumerate(result.data):
            if i >= len(sample_phones):
                break
                
            phone = sample_phones[i]
            location = sample_locations[i % len(sample_locations)]
            
            try:
                # Update user with phone number and location
                update_result = supabase.table('users').update({
                    'phone': phone,
                    'latitude': location['lat'],
                    'longitude': location['lon']
                }).eq('id', user['id']).execute()
                
                if update_result.data:
                    print(f"✅ Updated {user.get('name', user['id'])} with phone {phone}")
                    updated_count += 1
                else:
                    print(f"❌ Failed to update {user.get('name', user['id'])}")
                    
            except Exception as e:
                print(f"❌ Error updating {user.get('name', user['id'])}: {e}")
        
        print(f"\n🎉 Successfully updated {updated_count} users with phone numbers and locations")
        print("\n📱 Sample phone numbers added:")
        for i, phone in enumerate(sample_phones[:updated_count]):
            print(f"  {i+1}. {phone}")
        
        print("\n📍 Sample locations added:")
        for i, loc in enumerate(sample_locations[:updated_count]):
            print(f"  {i+1}. Lat: {loc['lat']}, Lon: {loc['lon']}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("📱 Adding phone numbers to users for SMS testing...")
    print("=" * 50)
    add_phone_numbers()
