import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.models.models import Product
from app.config.config import Config
import re
import math

class SkincareRecommender:
    """Skincare recommendation system using Content-Based Filtering and KNN"""
    
    def __init__(self):
        self.products_df = None
        self.tfidf_vectorizer = None
        self.tfidf_matrix = None
    
    def load_products(self):
        """Load products from database"""
        products = Product.get_all()
        if not products:
            return False
        
        self.products_df = pd.DataFrame(products)
        self._preprocess_data()
        self._build_content_features()
        return True
    
    def _preprocess_data(self):
        """Preprocess product data"""
        # Clean and normalize text data
        self.products_df['deskripsi_clean'] = self.products_df['description'].apply(self._clean_text)
        self.products_df['nama_clean'] = self.products_df['name'].apply(self._clean_text)
        
        # Combine text features for Content-Based Filtering
        self.products_df['combined_text'] = (
            self.products_df['nama_clean'] + ' ' + 
            self.products_df['brand'] + ' ' + 
            self.products_df['deskripsi_clean']
        )
    
    def _clean_text(self, text):
        """Clean and normalize text"""
        if pd.isna(text):
            return ""
        
        # Convert to lowercase
        text = str(text).lower()
        
        # Remove special characters and numbers
        text = re.sub(r'[^a-zA-Z\s]', ' ', text)
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text
    
    def _normalize_feature(self, feature):
        """Normalize numerical feature using Min-Max scaling"""
        min_val = feature.min()
        max_val = feature.max()
        
        if max_val == min_val:
            return feature * 0  # All values are the same
        
        return (feature - min_val) / (max_val - min_val)
    
    def _build_content_features(self):
        """Build TF-IDF features for content-based filtering"""
        # Create TF-IDF vectorizer
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=1000,
            stop_words=None,  # Indonesian stopwords not available in sklearn
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.8
        )
        
        # Fit and transform the combined text
        self.tfidf_matrix = self.tfidf_vectorizer.fit_transform(self.products_df['combined_text'])
    
    def _create_user_profile(self, preferences):
        """Create user profile vector from preferences"""
        # Create user query text based on preferences
        user_text_parts = []
        
        # Add skin condition keywords
        skin_condition_keywords = {
            'berminyak': 'oil control minyak sebum',
            'kering': 'moisturizer pelembab hydrating',
            'kombinasi': 'balance seimbang combination',
            'sensitif': 'gentle sensitive hypoallergenic',
            'normal': 'daily maintenance normal'
        }
        user_text_parts.append(skin_condition_keywords.get(preferences['kondisi_kulit'], ''))
        
        # Add skin problem keywords
        skin_problem_keywords = {
            'jerawat': 'acne anti jerawat salicylic',
            'komedo': 'blackhead whitehead pore',
            'kusam': 'brightening whitening vitamin c',
            'kerutan': 'anti aging retinol wrinkle',
            'flek_hitam': 'dark spot niacinamide',
            'pori_besar': 'pore minimizer tightening'
        }
        user_text_parts.append(skin_problem_keywords.get(preferences['masalah_kulit'], ''))
        
        # Add product preference keywords
        if preferences['preferensi_produk'] != 'semua':
            user_text_parts.append(preferences['preferensi_produk'])
        
        # Add user keywords if provided
        if preferences.get('kata_kunci_preferensi'):
            user_text_parts.append(preferences['kata_kunci_preferensi'])
        
        # Add search keywords if provided
        if preferences.get('kata_kunci'):
            user_text_parts.append(preferences['kata_kunci'])
        
        # Combine all text parts
        user_query = ' '.join(user_text_parts)
        user_query = self._clean_text(user_query)
        
        # Transform user query using existing TF-IDF vectorizer
        user_tfidf = self.tfidf_vectorizer.transform([user_query])
        
        return user_tfidf
    
    def get_recommendations(self, preferences, max_recommendations=10, k_value=None):
        """Get product recommendations using Content-Based Filtering and KNN"""
        # Load products if not already loaded
        if self.products_df is None:
            if not self.load_products():
                return []

        # Use provided k_value or default from config
        k = k_value if k_value is not None else Config.KNN_K_VALUE
        
        # Create user profile based on preferences
        user_features = self._create_user_profile(preferences)
        
        # Get content-based similarities using cosine similarity
        content_similarities = cosine_similarity(user_features, self.tfidf_matrix).flatten()
        
        # Calculate KNN distances for all products
        product_distances = []
        
        for idx, row in self.products_df.iterrows():
            # Get content similarity score for this product
            content_score = content_similarities[idx]
            
            # For KNN, we use content similarity as the main feature
            # The distance is simply 1 - cosine_similarity (closer to 1 = more similar)
            knn_distance = 1 - content_score
            
            # Store product with its distance and content similarity
            product_distances.append({
                'index': idx,
                'distance': knn_distance,
                'product': row.to_dict(),
                'content_similarity': content_score,
                'explanation': self._generate_explanation(content_score, preferences)
            })
        
        # Sort by KNN distance (ascending - smaller distance = more similar)
        product_distances.sort(key=lambda x: x['distance'])
        
        # Take top K nearest neighbors
        knn_recommendations = product_distances[:max_recommendations]
        
        # Convert to final format
        recommendations = []
        for item in knn_recommendations:
            recommendation = {
                'product': item['product'],
                'content_similarity': item['content_similarity'],
                'knn_distance': item['distance'],
                'explanation': item['explanation']
            }
            recommendations.append(recommendation)
        
        return recommendations
    
    def _generate_explanation(self, content_score, preferences):
        """Generate explanation for recommendation based on content similarity"""
        explanation_parts = []
        
        # Content similarity explanation
        if content_score > 0.7:
            explanation_parts.append("Sangat cocok dengan preferensi Anda")
        elif content_score > 0.5:
            explanation_parts.append("Cukup sesuai dengan preferensi Anda")
        elif content_score > 0.3:
            explanation_parts.append("Memiliki beberapa kesamaan dengan preferensi Anda")
        else:
            explanation_parts.append("Produk alternatif yang mungkin menarik")
        
        # Add specific preference matches
        if 'jenis_kulit' in preferences and preferences['jenis_kulit']:
            explanation_parts.append(f"untuk kulit {preferences['jenis_kulit']}")
        
        if 'masalah_kulit' in preferences and preferences['masalah_kulit']:
            explanation_parts.append(f"mengatasi {preferences['masalah_kulit']}")
        
        return " - ".join(explanation_parts)