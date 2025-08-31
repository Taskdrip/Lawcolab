#!/usr/bin/env python3
"""
Initialize sample law firm showcase data for testing
"""

from app import app, db
from models import LawFirm, LawFirmShowcase, PublicLawFirmReview, User, ROLE_ADMIN
from datetime import datetime
import secrets

def create_sample_showcases():
    """Create sample law firm showcases for testing"""
    
    with app.app_context():
        print("Creating sample law firm showcases...")
        
        # Sample law firms data
        sample_firms = [
            {
                'name': 'Morgan & Associates Law Firm',
                'description': 'Leading corporate law firm specializing in mergers & acquisitions, corporate governance, and business litigation.',
                'email': 'contact@morganlaw.com',
                'phone': '+1 (555) 123-4567',
                'address': '123 Corporate Plaza, New York, NY 10001',
                'website': 'https://morganlaw.com',
                'practice_areas': 'Corporate Law, M&A, Business Litigation, Securities Law',
                'showcase': {
                    'public_title': 'Morgan & Associates - Corporate Law Experts',
                    'public_description': 'With over 25 years of experience, Morgan & Associates has successfully guided Fortune 500 companies through complex mergers, acquisitions, and corporate restructuring. Our team of expert attorneys delivers strategic legal solutions that drive business success.',
                    'hero_image_url': 'https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=1200&h=400&fit=crop&crop=center',
                    'logo_image_url': 'https://images.unsplash.com/photo-1560472354-b33ff0c44a43?w=100&h=100&fit=crop&crop=center',
                    'linkedin_url': 'https://linkedin.com/company/morgan-associates',
                    'website_url': 'https://morganlaw.com'
                }
            },
            {
                'name': 'Davis Family Law Group',
                'description': 'Compassionate family law attorneys helping families navigate divorce, custody, and adoption matters.',
                'email': 'info@davisfamilylaw.com',
                'phone': '+1 (555) 234-5678',
                'address': '456 Family Court Blvd, Los Angeles, CA 90210',
                'website': 'https://davisfamilylaw.com',
                'practice_areas': 'Family Law, Divorce, Child Custody, Adoption, Domestic Relations',
                'showcase': {
                    'public_title': 'Davis Family Law Group - Protecting Families',
                    'public_description': 'At Davis Family Law Group, we understand that family matters require both legal expertise and emotional support. Our dedicated team provides personalized attention to each case, ensuring the best outcomes for you and your loved ones.',
                    'hero_image_url': 'https://images.unsplash.com/photo-1551836022-deb4988cc6c0?w=1200&h=400&fit=crop&crop=center',
                    'logo_image_url': 'https://images.unsplash.com/photo-1521737604893-d14cc237f11d?w=100&h=100&fit=crop&crop=center',
                    'facebook_url': 'https://facebook.com/davisfamilylaw',
                    'instagram_url': 'https://instagram.com/davisfamilylaw'
                }
            },
            {
                'name': 'Richardson Criminal Defense',
                'description': 'Aggressive criminal defense attorneys with a proven track record of protecting clients\' rights.',
                'email': 'defense@richardsonlaw.com',
                'phone': '+1 (555) 345-6789',
                'address': '789 Justice Avenue, Chicago, IL 60601',
                'website': 'https://richardsondefense.com',
                'practice_areas': 'Criminal Defense, DUI/DWI, White Collar Crime, Federal Cases',
                'showcase': {
                    'public_title': 'Richardson Criminal Defense - Your Rights Protected',
                    'public_description': 'When facing criminal charges, you need experienced attorneys who will fight tirelessly for your freedom. Richardson Criminal Defense has successfully defended over 1,000 cases with a 95% success rate in avoiding maximum penalties.',
                    'hero_image_url': 'https://images.unsplash.com/photo-1589829545856-d10d557cf95f?w=1200&h=400&fit=crop&crop=center',
                    'logo_image_url': 'https://images.unsplash.com/photo-1505664194779-8beaceb93744?w=100&h=100&fit=crop&crop=center',
                    'twitter_url': 'https://twitter.com/richardsonlaw',
                    'linkedin_url': 'https://linkedin.com/company/richardson-defense'
                }
            }
        ]
        
        for firm_data in sample_firms:
            # Check if law firm already exists
            existing_firm = LawFirm.query.filter_by(name=firm_data['name']).first()
            
            if not existing_firm:
                # Create law firm
                law_firm = LawFirm(
                    name=firm_data['name'],
                    description=firm_data['description'],
                    email=firm_data['email'],
                    phone=firm_data['phone'],
                    address=firm_data['address'],
                    website=firm_data['website'],
                    practice_areas=firm_data['practice_areas'],
                    admin_access_granted=True
                )
                
                db.session.add(law_firm)
                db.session.flush()  # Get the ID
                
                # Create admin user for the law firm
                admin_user = User(
                    id=secrets.token_urlsafe(16),
                    email=firm_data['email'],
                    first_name='Admin',
                    last_name=firm_data['name'].split()[0],
                    role=ROLE_ADMIN,
                    law_firm_id=law_firm.id,
                    active=True
                )
                
                db.session.add(admin_user)
                
                print(f"Created law firm: {law_firm.name}")
            else:
                law_firm = existing_firm
                print(f"Law firm already exists: {law_firm.name}")
            
            # Check if showcase already exists
            existing_showcase = LawFirmShowcase.query.filter_by(law_firm_id=law_firm.id).first()
            
            if not existing_showcase:
                # Create showcase
                showcase_data = firm_data['showcase']
                showcase = LawFirmShowcase(
                    law_firm_id=law_firm.id,
                    is_featured=True,
                    is_active=True,
                    showcase_order=len(sample_firms) - sample_firms.index(firm_data),  # Different order for each
                    public_title=showcase_data['public_title'],
                    public_description=showcase_data['public_description'],
                    hero_image_url=showcase_data.get('hero_image_url'),
                    logo_image_url=showcase_data.get('logo_image_url'),
                    website_url=showcase_data.get('website_url'),
                    facebook_url=showcase_data.get('facebook_url'),
                    linkedin_url=showcase_data.get('linkedin_url'),
                    twitter_url=showcase_data.get('twitter_url'),
                    instagram_url=showcase_data.get('instagram_url'),
                    total_reviews=0,
                    average_rating=5.0,
                    total_views=0
                )
                
                db.session.add(showcase)
                db.session.flush()  # Get the ID
                
                print(f"Created showcase for: {law_firm.name}")
                
                # Create sample reviews
                sample_reviews = [
                    {
                        'reviewer_name': 'John Smith',
                        'reviewer_company': 'Tech Startup Inc.',
                        'reviewer_location': 'San Francisco, CA',
                        'rating': 5,
                        'review_title': 'Outstanding Legal Service',
                        'review_text': 'The team provided exceptional guidance throughout our acquisition process. Their expertise and attention to detail were invaluable.'
                    },
                    {
                        'reviewer_name': 'Sarah Johnson',
                        'reviewer_company': 'Johnson Enterprises',
                        'reviewer_location': 'Austin, TX',
                        'rating': 5,
                        'review_title': 'Professional and Responsive',
                        'review_text': 'Highly professional service with quick responses to all our questions. They made a complex legal process seem straightforward.'
                    },
                    {
                        'reviewer_name': 'Michael Brown',
                        'reviewer_location': 'Seattle, WA',
                        'rating': 4,
                        'review_title': 'Great Experience',
                        'review_text': 'Very satisfied with the service provided. The lawyers were knowledgeable and kept us informed throughout the entire process.'
                    }
                ]
                
                for review_data in sample_reviews:
                    review = PublicLawFirmReview(
                        showcase_id=showcase.id,
                        reviewer_name=review_data['reviewer_name'],
                        reviewer_company=review_data.get('reviewer_company'),
                        reviewer_location=review_data.get('reviewer_location'),
                        rating=review_data['rating'],
                        review_title=review_data['review_title'],
                        review_text=review_data['review_text'],
                        is_approved=True,
                        is_featured=True,
                        is_visible=True
                    )
                    
                    db.session.add(review)
                
                # Update showcase stats
                showcase.total_reviews = len(sample_reviews)
                showcase.average_rating = sum(r['rating'] for r in sample_reviews) / len(sample_reviews)
                
                print(f"Created {len(sample_reviews)} sample reviews for {law_firm.name}")
            else:
                print(f"Showcase already exists for: {law_firm.name}")
        
        db.session.commit()
        print("\nSample law firm showcases created successfully!")
        print("You can now view them on the homepage and manage them from the super admin dashboard.")

if __name__ == "__main__":
    create_sample_showcases()