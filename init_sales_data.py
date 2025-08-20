"""
Initialize sales data with sample reviews and settings
"""
from app import app, db
from models import CustomerReview, PopupSettings

def init_sales_data():
    """Initialize popup settings and sample customer reviews"""
    with app.app_context():
        # Create or update popup settings
        settings = PopupSettings.query.first()
        if not settings:
            settings = PopupSettings()
            settings.popup_delay_seconds = 7
            settings.popup_enabled = True
            settings.welcome_video_url = ""
            settings.thankyou_video_url = ""
            settings.starter_price = 29.00
            settings.growth_price = 79.00
            settings.scale_price = 199.00
            settings.lifetime_price = 999.00
            db.session.add(settings)
            print("✓ Created popup settings")
        
        # Sample reviews data
        sample_reviews = [
            {
                "name": "Sarah Mitchell",
                "firm_name": "Mitchell & Associates",
                "review_text": "LawColab transformed our practice! The client management system is intuitive and the invoicing features saved us hours every week. Our productivity increased by 40% in just 3 months.",
                "rating": 5,
                "location": "New York, NY",
                "is_featured": True
            },
            {
                "name": "Michael Rodriguez",
                "firm_name": "Rodriguez Law Group",
                "review_text": "Outstanding platform! The multi-currency invoicing is perfect for our international clients. Customer support is exceptional - they helped us migrate from our old system seamlessly.",
                "rating": 5,
                "location": "Miami, FL",
                "is_featured": True
            },
            {
                "name": "Jennifer Chen",
                "firm_name": "Chen Legal Services",
                "review_text": "The analytics dashboard gives us incredible insights into our firm's performance. We can now make data-driven decisions that have significantly improved our profitability.",
                "rating": 5,
                "location": "San Francisco, CA",
                "is_featured": True
            },
            {
                "name": "David Thompson",
                "firm_name": "Thompson & Partners",
                "review_text": "Best investment we've made for our firm. The project management features keep our team organized and clients are impressed with our professional invoicing and communication.",
                "rating": 5,
                "location": "London, UK",
                "is_featured": False
            },
            {
                "name": "Maria Gonzalez",
                "firm_name": "Gonzalez Family Law",
                "review_text": "LawColab's client portal has revolutionized how we communicate with clients. They can track their case progress in real-time, reducing calls and emails by 60%.",
                "rating": 5,
                "location": "Austin, TX",
                "is_featured": False
            },
            {
                "name": "Robert Johnson",
                "firm_name": "Johnson Criminal Defense",
                "review_text": "The document management system is incredible. We can access case files from anywhere, and the security features give us peace of mind with confidential client information.",
                "rating": 5,
                "location": "Chicago, IL",
                "is_featured": False
            },
            {
                "name": "Lisa Wong",
                "firm_name": "Wong IP Law",
                "review_text": "The time tracking and billing integration is seamless. We've eliminated billing disputes and improved cash flow with accurate, detailed invoices generated automatically.",
                "rating": 5,
                "location": "Seattle, WA",
                "is_featured": False
            },
            {
                "name": "James Williams",
                "firm_name": "Williams Corporate Law",
                "review_text": "Outstanding customer service and an even better product. The customization options allowed us to tailor LawColab perfectly to our corporate law practice needs.",
                "rating": 5,
                "location": "Dallas, TX",
                "is_featured": False
            },
            {
                "name": "Amanda Brown",
                "firm_name": "Brown Estate Planning",
                "review_text": "The client intake process is now completely automated. New clients can schedule consultations and upload documents through the portal. It's saving us 10+ hours per week.",
                "rating": 5,
                "location": "Phoenix, AZ",
                "is_featured": False
            },
            {
                "name": "Christopher Lee",
                "firm_name": "Lee Immigration Law",
                "review_text": "The multilingual support and international features make LawColab perfect for our diverse client base. Case tracking across different jurisdictions is now effortless.",
                "rating": 5,
                "location": "Los Angeles, CA",
                "is_featured": False
            },
            {
                "name": "Nicole Taylor",
                "firm_name": "Taylor Personal Injury",
                "review_text": "The mobile app keeps me connected to my practice 24/7. I can review cases, approve invoices, and communicate with clients from anywhere. Game-changing for busy attorneys.",
                "rating": 5,
                "location": "Atlanta, GA",
                "is_featured": False
            },
            {
                "name": "Kevin Miller",
                "firm_name": "Miller Real Estate Law",
                "review_text": "LawColab's integration with our accounting software eliminated double data entry. The financial reports help us understand which practice areas are most profitable.",
                "rating": 5,
                "location": "Denver, CO",
                "is_featured": False
            },
            {
                "name": "Rachel Davis",
                "firm_name": "Davis Employment Law",
                "review_text": "The compliance tracking features are exceptional. We never miss deadlines with automatic reminders and the audit trail keeps us protected during reviews.",
                "rating": 5,
                "location": "Boston, MA",
                "is_featured": False
            },
            {
                "name": "Andrew Wilson",
                "firm_name": "Wilson Tax Law",
                "review_text": "The client collaboration tools are fantastic. Clients can review documents, approve strategies, and provide feedback directly through the platform. Very efficient.",
                "rating": 5,
                "location": "Nashville, TN",
                "is_featured": False
            },
            {
                "name": "Patricia Garcia",
                "firm_name": "Garcia Bankruptcy Law",
                "review_text": "The matter-based organization keeps all case information in one place. No more searching through emails or paper files. Everything is searchable and instantly accessible.",
                "rating": 5,
                "location": "Las Vegas, NV",
                "is_featured": False
            },
            {
                "name": "Mark Anderson",
                "firm_name": "Anderson Environmental Law",
                "review_text": "The environmental compliance tracking modules are perfectly suited to our practice. Regulatory deadlines, document management, and client reporting all in one system.",
                "rating": 5,
                "location": "Portland, OR",
                "is_featured": False
            },
            {
                "name": "Stephanie Martin",
                "firm_name": "Martin Family Law",
                "review_text": "The calendar integration and conflict checking saved us from several potential scheduling disasters. The family law workflows are tailored perfectly to our needs.",
                "rating": 5,
                "location": "Charlotte, NC",
                "is_featured": False
            },
            {
                "name": "Daniel Clark",
                "firm_name": "Clark Construction Law",
                "review_text": "The project milestone tracking and payment schedules are perfect for construction law. Clients love the transparency and we've improved payment collection by 35%.",
                "rating": 5,
                "location": "Houston, TX",
                "is_featured": False
            },
            {
                "name": "Michelle Lewis",
                "firm_name": "Lewis Healthcare Law",
                "review_text": "HIPAA compliance features and secure client communication make LawColab essential for healthcare law. The privacy protections exceed industry standards.",
                "rating": 5,
                "location": "Philadelphia, PA",
                "is_featured": False
            },
            {
                "name": "Ryan Turner",
                "firm_name": "Turner Sports Law",
                "review_text": "Managing athlete contracts and endorsement deals is so much easier with LawColab. The contract comparison tools and deadline tracking are invaluable for sports law.",
                "rating": 5,
                "location": "Orlando, FL",
                "is_featured": False
            }
        ]
        
        # Check if reviews already exist
        existing_reviews = CustomerReview.query.count()
        if existing_reviews == 0:
            for review_data in sample_reviews:
                review = CustomerReview()
                review.name = review_data['name']
                review.firm_name = review_data['firm_name']
                review.review_text = review_data['review_text']
                review.rating = review_data['rating']
                review.location = review_data['location']
                review.is_featured = review_data['is_featured']
                review.is_active = True
                db.session.add(review)
            
            db.session.commit()
            print(f"✓ Created {len(sample_reviews)} customer reviews")
        else:
            print(f"✓ Reviews already exist ({existing_reviews} reviews)")

if __name__ == "__main__":
    init_sales_data()
    print("✓ Sales data initialization complete!")