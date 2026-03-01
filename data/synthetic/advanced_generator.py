"""
Advanced Synthetic Architecture Generator
Creates realistic cloud architectures for any pattern
"""

import json
import random
from datetime import datetime
from typing import List, Dict, Tuple
from enum import Enum
from dataclasses import dataclass, asdict

class ArchitecturePattern(Enum):
    """Common architecture patterns"""
    ECOMMERCE = "ecommerce"
    SAAS = "saas"
    GAMING = "gaming"
    DATA_PIPELINE = "data_pipeline"
    MICROSERVICES = "microservices"
    MONOLITH = "monolith"
    SERVERLESS = "serverless"
    IOT = "iot"
    ML_PLATFORM = "ml_platform"
    MEDIA_STREAMING = "media_streaming"

class ServiceTemplate:
    """Template for generating services"""
    
    # AWS Service Types with realistic costs
    SERVICE_TYPES = {
        'api': {
            'type': 'service',
            'instance_types': ['t3.small', 't3.medium', 't3.large', 't3.xlarge'],
            'cost_per_instance': [15, 30, 60, 120],  # Monthly
            'typical_count': [2, 5, 10, 20]
        },
        'web': {
            'type': 'service',
            'instance_types': ['t3.micro', 't3.small', 't3.medium'],
            'cost_per_instance': [7, 15, 30],
            'typical_count': [3, 5, 10]
        },
        'worker': {
            'type': 'batch',
            'instance_types': ['c5.large', 'c5.xlarge', 'c5.2xlarge'],
            'cost_per_instance': [60, 120, 240],
            'typical_count': [2, 5, 10]
        },
        'database_postgres': {
            'type': 'database',
            'instance_types': ['db.t3.medium', 'db.m5.large', 'db.m5.xlarge', 'db.m5.2xlarge'],
            'cost_per_instance': [50, 120, 240, 480],
            'typical_count': [1, 1, 2, 2]  # Primary + replica
        },
        'database_mysql': {
            'type': 'database',
            'instance_types': ['db.t3.small', 'db.m5.large', 'db.m5.xlarge'],
            'cost_per_instance': [35, 120, 240],
            'typical_count': [1, 1, 2]
        },
        'database_mongodb': {
            'type': 'database',
            'instance_types': ['r5.large', 'r5.xlarge', 'r5.2xlarge'],
            'cost_per_instance': [100, 200, 400],
            'typical_count': [3, 3, 5]  # Replica set
        },
        'cache_redis': {
            'type': 'cache',
            'instance_types': ['cache.t3.small', 'cache.m5.large', 'cache.m5.xlarge'],
            'cost_per_instance': [25, 100, 200],
            'typical_count': [1, 2, 3]
        },
        'cache_memcached': {
            'type': 'cache',
            'instance_types': ['cache.t3.medium', 'cache.m5.large'],
            'cost_per_instance': [35, 100],
            'typical_count': [2, 3]
        },
        's3': {
            'type': 'storage',
            'storage_classes': ['STANDARD', 'INTELLIGENT_TIERING', 'GLACIER'],
            'cost_per_gb': [0.023, 0.018, 0.004],
            'typical_size_gb': [1000, 5000, 10000, 50000]
        },
        'lambda': {
            'type': 'serverless',
            'memory_mb': [128, 256, 512, 1024, 2048],
            'cost_per_million': [0.20, 0.40, 0.83, 1.67, 3.34],
            'typical_invocations': [100000, 1000000, 10000000]
        },
        'queue_sqs': {
            'type': 'queue',
            'cost_per_million': 0.40,
            'typical_messages': [1000000, 10000000, 100000000]
        },
        'load_balancer': {
            'type': 'load_balancer',
            'lb_types': ['ALB', 'NLB'],
            'cost_per_hour': [0.025, 0.027],
            'typical_count': [1, 2]
        },
        'cdn_cloudfront': {
            'type': 'cdn',
            'cost_per_gb': [0.085],
            'typical_size_gb': [1000, 10000, 100000]
        },
        'search_elasticsearch': {
            'type': 'search',
            'instance_types': ['t3.small.search', 'm5.large.search', 'r5.large.search'],
            'cost_per_instance': [30, 150, 180],
            'typical_count': [1, 3, 3]
        }
    }

class ArchitectureGenerator:
    """Generate complete architectures"""
    
    def __init__(self, pattern: ArchitecturePattern, complexity: str = "medium"):
        self.pattern = pattern
        self.complexity = complexity  # small, medium, large, xlarge
        self.services = []
        self.dependencies = []
        self.service_counter = {}
        
    def generate(self) -> Dict:
        """Generate complete architecture"""
        
        if self.pattern == ArchitecturePattern.ECOMMERCE:
            return self._generate_ecommerce()
        elif self.pattern == ArchitecturePattern.SAAS:
            return self._generate_saas()
        elif self.pattern == ArchitecturePattern.GAMING:
            return self._generate_gaming()
        elif self.pattern == ArchitecturePattern.DATA_PIPELINE:
            return self._generate_data_pipeline()
        elif self.pattern == ArchitecturePattern.MICROSERVICES:
            return self._generate_microservices()
        elif self.pattern == ArchitecturePattern.SERVERLESS:
            return self._generate_serverless()
        elif self.pattern == ArchitecturePattern.ML_PLATFORM:
            return self._generate_ml_platform()
        elif self.pattern == ArchitecturePattern.MEDIA_STREAMING:
            return self._generate_media_streaming()
        else:
            return self._generate_generic()
    
    def _generate_ecommerce(self) -> Dict:
        """E-commerce platform architecture"""
        
        # Frontend
        web_id = self._add_service('web', 'storefront-web', 'frontend-team')
        cdn_id = self._add_service('cdn_cloudfront', 'cdn-assets', 'frontend-team')
        
        # API Layer
        api_id = self._add_service('api', 'product-api', 'backend-team')
        cart_api_id = self._add_service('api', 'cart-api', 'backend-team')
        order_api_id = self._add_service('api', 'order-api', 'backend-team')
        
        # Databases
        product_db_id = self._add_service('database_postgres', 'product-db', 'backend-team')
        order_db_id = self._add_service('database_postgres', 'order-db', 'backend-team')
        
        # Cache
        redis_id = self._add_service('cache_redis', 'session-cache', 'backend-team')
        
        # Storage
        product_images_id = self._add_service('s3', 'product-images', 'backend-team')
        
        # Background Jobs
        order_processor_id = self._add_service('worker', 'order-processor', 'backend-team')
        email_worker_id = self._add_service('worker', 'email-worker', 'backend-team')
        
        # Queue
        order_queue_id = self._add_service('queue_sqs', 'order-queue', 'backend-team')
        
        # Search
        search_id = self._add_service('search_elasticsearch', 'product-search', 'backend-team')
        
        # Load Balancer
        lb_id = self._add_service('load_balancer', 'main-alb', 'infra-team')
        
        # Dependencies
        self._add_dependency(web_id, cdn_id, 'reads_from', 0.9)
        self._add_dependency(web_id, lb_id, 'calls', 1.0)
        self._add_dependency(lb_id, api_id, 'routes_to', 1.0)
        self._add_dependency(lb_id, cart_api_id, 'routes_to', 0.8)
        self._add_dependency(lb_id, order_api_id, 'routes_to', 0.5)
        
        self._add_dependency(api_id, product_db_id, 'reads_from', 0.9)
        self._add_dependency(api_id, redis_id, 'reads_from', 0.95)
        self._add_dependency(api_id, search_id, 'reads_from', 0.7)
        self._add_dependency(api_id, product_images_id, 'reads_from', 0.6)
        
        self._add_dependency(cart_api_id, redis_id, 'reads_from', 1.0)
        self._add_dependency(cart_api_id, product_db_id, 'reads_from', 0.5)
        
        self._add_dependency(order_api_id, order_db_id, 'writes_to', 1.0)
        self._add_dependency(order_api_id, order_queue_id, 'writes_to', 1.0)
        
        self._add_dependency(order_processor_id, order_queue_id, 'reads_from', 1.0)
        self._add_dependency(order_processor_id, order_db_id, 'writes_to', 1.0)
        
        self._add_dependency(email_worker_id, order_queue_id, 'reads_from', 0.3)
        
        return self._build_architecture('E-commerce Platform')
    
    def _generate_saas(self) -> Dict:
        """SaaS application architecture"""
        
        # Multi-tenant API
        api_id = self._add_service('api', 'tenant-api', 'platform-team')
        auth_id = self._add_service('api', 'auth-service', 'platform-team')
        
        # Databases
        tenant_db_id = self._add_service('database_postgres', 'tenant-db', 'platform-team')
        analytics_db_id = self._add_service('database_postgres', 'analytics-db', 'data-team')
        
        # Cache
        redis_id = self._add_service('cache_redis', 'session-cache', 'platform-team')
        
        # Background Processing
        report_worker_id = self._add_service('worker', 'report-generator', 'data-team')
        notification_worker_id = self._add_service('worker', 'notification-service', 'platform-team')
        
        # Queue
        job_queue_id = self._add_service('queue_sqs', 'job-queue', 'platform-team')
        
        # Storage
        tenant_data_id = self._add_service('s3', 'tenant-data', 'platform-team')
        reports_id = self._add_service('s3', 'generated-reports', 'data-team')
        
        # Dependencies
        self._add_dependency(api_id, auth_id, 'calls', 1.0)
        self._add_dependency(api_id, tenant_db_id, 'reads_from', 0.9)
        self._add_dependency(api_id, redis_id, 'reads_from', 0.95)
        self._add_dependency(api_id, tenant_data_id, 'writes_to', 0.4)
        self._add_dependency(api_id, job_queue_id, 'writes_to', 0.3)
        
        self._add_dependency(auth_id, tenant_db_id, 'reads_from', 1.0)
        self._add_dependency(auth_id, redis_id, 'writes_to', 1.0)
        
        self._add_dependency(report_worker_id, job_queue_id, 'reads_from', 1.0)
        self._add_dependency(report_worker_id, analytics_db_id, 'reads_from', 1.0)
        self._add_dependency(report_worker_id, reports_id, 'writes_to', 1.0)
        
        self._add_dependency(notification_worker_id, job_queue_id, 'reads_from', 0.5)
        
        return self._build_architecture('SaaS Platform')
    
    def _generate_gaming(self) -> Dict:
        """Gaming platform architecture"""
        
        # Game Servers
        game_server_id = self._add_service('api', 'game-server', 'game-team', scale_multiplier=3)
        matchmaking_id = self._add_service('api', 'matchmaking-service', 'game-team')
        
        # Real-time
        session_server_id = self._add_service('api', 'session-server', 'game-team', scale_multiplier=2)
        
        # Databases
        player_db_id = self._add_service('database_mongodb', 'player-db', 'game-team')
        leaderboard_db_id = self._add_service('cache_redis', 'leaderboard-cache', 'game-team')
        
        # Storage
        game_assets_id = self._add_service('s3', 'game-assets', 'game-team', scale_multiplier=5)
        player_data_id = self._add_service('s3', 'player-saves', 'game-team')
        
        # CDN
        cdn_id = self._add_service('cdn_cloudfront', 'asset-cdn', 'game-team', scale_multiplier=3)
        
        # Analytics
        analytics_worker_id = self._add_service('worker', 'game-analytics', 'data-team')
        analytics_db_id = self._add_service('database_postgres', 'analytics-db', 'data-team')
        
        # Dependencies
        self._add_dependency(game_server_id, session_server_id, 'calls', 1.0)
        self._add_dependency(game_server_id, player_db_id, 'reads_from', 0.8)
        self._add_dependency(game_server_id, leaderboard_db_id, 'writes_to', 0.6)
        self._add_dependency(game_server_id, game_assets_id, 'reads_from', 0.3)
        
        self._add_dependency(matchmaking_id, player_db_id, 'reads_from', 1.0)
        self._add_dependency(matchmaking_id, session_server_id, 'calls', 1.0)
        
        self._add_dependency(session_server_id, player_db_id, 'reads_from', 0.9)
        self._add_dependency(session_server_id, player_data_id, 'writes_to', 0.4)
        
        self._add_dependency(analytics_worker_id, player_db_id, 'reads_from', 1.0)
        self._add_dependency(analytics_worker_id, analytics_db_id, 'writes_to', 1.0)
        
        self._add_dependency(cdn_id, game_assets_id, 'reads_from', 1.0)
        
        return self._build_architecture('Gaming Platform')
    
    def _generate_data_pipeline(self) -> Dict:
        """Data pipeline architecture"""
        
        # Ingestion
        ingest_api_id = self._add_service('api', 'data-ingest-api', 'data-team')
        
        # Streaming
        stream_processor_id = self._add_service('worker', 'stream-processor', 'data-team', scale_multiplier=2)
        
        # Storage
        raw_data_id = self._add_service('s3', 'raw-data-lake', 'data-team', scale_multiplier=10)
        processed_data_id = self._add_service('s3', 'processed-data', 'data-team', scale_multiplier=5)
        
        # Processing
        etl_worker_id = self._add_service('worker', 'etl-pipeline', 'data-team', scale_multiplier=3)
        
        # Analytics
        analytics_db_id = self._add_service('database_postgres', 'analytics-db', 'data-team')
        
        # Queue
        data_queue_id = self._add_service('queue_sqs', 'data-queue', 'data-team')
        
        # BI/Reporting
        reporting_api_id = self._add_service('api', 'reporting-api', 'analytics-team')
        
        # Dependencies
        self._add_dependency(ingest_api_id, raw_data_id, 'writes_to', 1.0)
        self._add_dependency(ingest_api_id, data_queue_id, 'writes_to', 1.0)
        
        self._add_dependency(stream_processor_id, data_queue_id, 'reads_from', 1.0)
        self._add_dependency(stream_processor_id, raw_data_id, 'writes_to', 1.0)
        
        self._add_dependency(etl_worker_id, raw_data_id, 'reads_from', 1.0)
        self._add_dependency(etl_worker_id, processed_data_id, 'writes_to', 1.0)
        self._add_dependency(etl_worker_id, analytics_db_id, 'writes_to', 0.8)
        
        self._add_dependency(reporting_api_id, analytics_db_id, 'reads_from', 1.0)
        self._add_dependency(reporting_api_id, processed_data_id, 'reads_from', 0.5)
        
        return self._build_architecture('Data Pipeline')
    
    def _generate_microservices(self) -> Dict:
        """Microservices architecture"""
        
        num_services = {'small': 5, 'medium': 10, 'large': 20, 'xlarge': 50}.get(self.complexity, 10)
        
        # API Gateway
        gateway_id = self._add_service('load_balancer', 'api-gateway', 'platform-team')
        
        # Service Mesh
        service_ids = []
        service_names = ['user', 'product', 'order', 'payment', 'inventory', 
                        'shipping', 'notification', 'analytics', 'recommendation', 'search']
        
        for i in range(min(num_services, len(service_names))):
            service_id = self._add_service('api', f'{service_names[i]}-service', f'{service_names[i]}-team')
            service_ids.append(service_id)
        
        # Shared Services
        cache_id = self._add_service('cache_redis', 'shared-cache', 'platform-team')
        message_queue_id = self._add_service('queue_sqs', 'message-bus', 'platform-team')
        
        # Per-service databases
        db_ids = []
        for i in range(min(num_services, len(service_names))):
            db_id = self._add_service('database_postgres', f'{service_names[i]}-db', f'{service_names[i]}-team')
            db_ids.append(db_id)
        
        # Dependencies - Gateway to services
        for service_id in service_ids:
            self._add_dependency(gateway_id, service_id, 'routes_to', 0.8)
        
        # Dependencies - Services to their databases
        for i, service_id in enumerate(service_ids):
            if i < len(db_ids):
                self._add_dependency(service_id, db_ids[i], 'reads_from', 0.9)
                self._add_dependency(service_id, cache_id, 'reads_from', 0.7)
                self._add_dependency(service_id, message_queue_id, 'writes_to', 0.3)
        
        # Inter-service dependencies (some services call others)
        if len(service_ids) >= 4:
            self._add_dependency(service_ids[2], service_ids[0], 'calls', 0.6)  # order -> user
            self._add_dependency(service_ids[2], service_ids[1], 'calls', 0.8)  # order -> product
            if len(service_ids) >= 5:
                self._add_dependency(service_ids[2], service_ids[3], 'calls', 0.9)  # order -> payment
        
        return self._build_architecture('Microservices Platform')
    
    def _generate_serverless(self) -> Dict:
        """Serverless architecture"""
        
        # API Gateway
        gateway_id = self._add_service('load_balancer', 'api-gateway', 'backend-team')
        
        # Lambda Functions
        auth_lambda_id = self._add_service('lambda', 'auth-function', 'backend-team')
        create_lambda_id = self._add_service('lambda', 'create-function', 'backend-team')
        read_lambda_id = self._add_service('lambda', 'read-function', 'backend-team')
        update_lambda_id = self._add_service('lambda', 'update-function', 'backend-team')
        delete_lambda_id = self._add_service('lambda', 'delete-function', 'backend-team')
        
        # Storage
        db_id = self._add_service('database_postgres', 'main-db', 'backend-team')
        s3_id = self._add_service('s3', 'user-data', 'backend-team')
        
        # Queue
        queue_id = self._add_service('queue_sqs', 'event-queue', 'backend-team')
        
        # Event Processing
        processor_lambda_id = self._add_service('lambda', 'event-processor', 'backend-team', scale_multiplier=2)
        
        # Dependencies
        self._add_dependency(gateway_id, auth_lambda_id, 'routes_to', 1.0)
        self._add_dependency(gateway_id, create_lambda_id, 'routes_to', 0.3)
        self._add_dependency(gateway_id, read_lambda_id, 'routes_to', 0.8)
        self._add_dependency(gateway_id, update_lambda_id, 'routes_to', 0.4)
        self._add_dependency(gateway_id, delete_lambda_id, 'routes_to', 0.2)
        
        self._add_dependency(create_lambda_id, db_id, 'writes_to', 1.0)
        self._add_dependency(create_lambda_id, queue_id, 'writes_to', 1.0)
        
        self._add_dependency(read_lambda_id, db_id, 'reads_from', 1.0)
        self._add_dependency(read_lambda_id, s3_id, 'reads_from', 0.4)
        
        self._add_dependency(update_lambda_id, db_id, 'writes_to', 1.0)
        self._add_dependency(delete_lambda_id, db_id, 'writes_to', 1.0)
        
        self._add_dependency(processor_lambda_id, queue_id, 'reads_from', 1.0)
        self._add_dependency(processor_lambda_id, s3_id, 'writes_to', 0.6)
        
        return self._build_architecture('Serverless Application')
    
    def _generate_ml_platform(self) -> Dict:
        """ML platform architecture"""
        
        # API
        inference_api_id = self._add_service('api', 'inference-api', 'ml-team')
        training_api_id = self._add_service('api', 'training-api', 'ml-team')
        
        # Model Storage
        model_storage_id = self._add_service('s3', 'model-artifacts', 'ml-team', scale_multiplier=3)
        
        # Training
        training_worker_id = self._add_service('worker', 'training-job', 'ml-team', scale_multiplier=5)
        
        # Feature Store
        feature_db_id = self._add_service('database_postgres', 'feature-store', 'ml-team')
        feature_cache_id = self._add_service('cache_redis', 'feature-cache', 'ml-team')
        
        # Data Lake
        training_data_id = self._add_service('s3', 'training-data', 'data-team', scale_multiplier=10)
        
        # Experiment Tracking
        experiment_db_id = self._add_service('database_postgres', 'experiment-tracking', 'ml-team')
        
        # Queue
        training_queue_id = self._add_service('queue_sqs', 'training-queue', 'ml-team')
        
        # Dependencies
        self._add_dependency(inference_api_id, model_storage_id, 'reads_from', 1.0)
        self._add_dependency(inference_api_id, feature_cache_id, 'reads_from', 0.9)
        self._add_dependency(inference_api_id, feature_db_id, 'reads_from', 0.3)
        
        self._add_dependency(training_api_id, training_queue_id, 'writes_to', 1.0)
        
        self._add_dependency(training_worker_id, training_queue_id, 'reads_from', 1.0)
        self._add_dependency(training_worker_id, training_data_id, 'reads_from', 1.0)
        self._add_dependency(training_worker_id, feature_db_id, 'reads_from', 0.8)
        self._add_dependency(training_worker_id, model_storage_id, 'writes_to', 1.0)
        self._add_dependency(training_worker_id, experiment_db_id, 'writes_to', 1.0)
        
        return self._build_architecture('ML Platform')
    
    def _generate_media_streaming(self) -> Dict:
        """Media streaming platform"""
        
        # API
        api_id = self._add_service('api', 'content-api', 'backend-team')
        
        # CDN
        cdn_id = self._add_service('cdn_cloudfront', 'video-cdn', 'media-team', scale_multiplier=10)
        
        # Storage
        video_storage_id = self._add_service('s3', 'video-content', 'media-team', scale_multiplier=50)
        thumbnail_storage_id = self._add_service('s3', 'thumbnails', 'media-team')
        
        # Transcoding
        transcoder_id = self._add_service('worker', 'video-transcoder', 'media-team', scale_multiplier=8)
        
        # Database
        metadata_db_id = self._add_service('database_postgres', 'content-metadata', 'backend-team')
        
        # Cache
        cache_id = self._add_service('cache_redis', 'metadata-cache', 'backend-team')
        
        # Queue
        transcode_queue_id = self._add_service('queue_sqs', 'transcode-queue', 'media-team')
        
        # Analytics
        analytics_worker_id = self._add_service('worker', 'view-analytics', 'analytics-team')
        analytics_db_id = self._add_service('database_postgres', 'analytics-db', 'analytics-team')
        
        # Dependencies
        self._add_dependency(api_id, metadata_db_id, 'reads_from', 0.9)
        self._add_dependency(api_id, cache_id, 'reads_from', 0.95)
        self._add_dependency(api_id, video_storage_id, 'writes_to', 0.1)
        self._add_dependency(api_id, transcode_queue_id, 'writes_to', 0.1)
        
        self._add_dependency(cdn_id, video_storage_id, 'reads_from', 1.0)
        self._add_dependency(cdn_id, thumbnail_storage_id, 'reads_from', 0.8)
        
        self._add_dependency(transcoder_id, transcode_queue_id, 'reads_from', 1.0)
        self._add_dependency(transcoder_id, video_storage_id, 'reads_from', 1.0)
        self._add_dependency(transcoder_id, video_storage_id, 'writes_to', 1.0)
        
        self._add_dependency(analytics_worker_id, metadata_db_id, 'reads_from', 1.0)
        self._add_dependency(analytics_worker_id, analytics_db_id, 'writes_to', 1.0)
        
        return self._build_architecture('Media Streaming Platform')
    
    def _generate_generic(self) -> Dict:
        """Generic architecture"""
        api_id = self._add_service('api', 'main-api', 'backend-team')
        db_id = self._add_service('database_postgres', 'main-db', 'backend-team')
        cache_id = self._add_service('cache_redis', 'cache', 'backend-team')
        
        self._add_dependency(api_id, db_id, 'reads_from', 0.9)
        self._add_dependency(api_id, cache_id, 'reads_from', 0.8)
        
        return self._build_architecture('Generic Application')
    
    def _add_service(self, service_type: str, name: str, owner: str, scale_multiplier: float = 1.0) -> str:
        """Add a service to the architecture"""
        
        if service_type not in self.service_counter:
            self.service_counter[service_type] = 1
        else:
            self.service_counter[service_type] += 1
        
        service_id = f"{service_type}-{self.service_counter[service_type]:03d}"
        
        template = ServiceTemplate.SERVICE_TYPES[service_type]
        
        # Calculate cost based on complexity and scale multiplier
        complexity_scale = {'small': 0.5, 'medium': 1.0, 'large': 2.0, 'xlarge': 4.0}.get(self.complexity, 1.0)
        
        if service_type in ['s3', 'cdn_cloudfront']:
            # Storage-based pricing
            size_idx = random.randint(0, len(template['typical_size_gb']) - 1)
            size_gb = template['typical_size_gb'][size_idx] * complexity_scale * scale_multiplier
            cost = size_gb * template['cost_per_gb'][0] if 'cost_per_gb' in template else template['cost_per_gb']
            
            attributes = {
                'size_gb': int(size_gb),
                'storage_class': template.get('storage_classes', ['STANDARD'])[0] if 'storage_classes' in template else None
            }
        
        elif service_type == 'lambda':
            # Lambda pricing
            memory_idx = random.randint(0, len(template['memory_mb']) - 1)
            memory = template['memory_mb'][memory_idx]
            invocations = template['typical_invocations'][random.randint(0, 2)] * complexity_scale * scale_multiplier
            cost = (invocations / 1000000) * template['cost_per_million'][memory_idx]
            
            attributes = {
                'memory_mb': memory,
                'invocations_monthly': int(invocations)
            }
        
        elif service_type == 'queue_sqs':
            # Queue pricing
            messages = template['typical_messages'][random.randint(0, 2)] * complexity_scale * scale_multiplier
            cost = (messages / 1000000) * template['cost_per_million']
            
            attributes = {
                'messages_monthly': int(messages)
            }
        
        elif service_type == 'load_balancer':
            # LB pricing
            lb_idx = random.randint(0, len(template['lb_types']) - 1)
            lb_type = template['lb_types'][lb_idx]
            count = template['typical_count'][lb_idx] * complexity_scale * scale_multiplier
            cost = template['cost_per_hour'][lb_idx] * 720 * count
            
            attributes = {
                'lb_type': lb_type,
                'count': int(count)
            }
        
        else:
            # Instance-based pricing
            instance_idx = random.randint(0, len(template['instance_types']) - 1)
            instance_type = template['instance_types'][instance_idx]
            instance_count = int(template['typical_count'][instance_idx] * complexity_scale * scale_multiplier)
            cost = template['cost_per_instance'][instance_idx] * instance_count
            
            attributes = {
                'instance_type': instance_type,
                'instance_count': instance_count
            }
        
        service = {
            'id': service_id,
            'name': name,
            'type': template['type'],
            'environment': 'production',
            'owner': owner,
            'cost_monthly': round(cost, 2),
            'attributes': attributes
        }
        
        self.services.append(service)
        return service_id
    
    def _add_dependency(self, source: str, target: str, dep_type: str, weight: float):
        """Add a dependency between services"""
        self.dependencies.append({
            'source': source,
            'target': target,
            'type': dep_type,
            'weight': weight
        })
    
    def _build_architecture(self, name: str) -> Dict:
        """Build final architecture dictionary"""
        return {
            'metadata': {
                'name': name,
                'pattern': self.pattern.value,
                'complexity': self.complexity,
                'environment': 'production',
                'region': 'us-east-1',
                'generated_at': datetime.now().isoformat(),
                'total_services': len(self.services),
                'total_cost_monthly': sum(s['cost_monthly'] for s in self.services)
            },
            'services': self.services,
            'dependencies': self.dependencies
        }

def generate_all_patterns(output_dir: str = '.'):
    """Generate all architecture patterns"""
    
    patterns = [
        (ArchitecturePattern.ECOMMERCE, 'medium'),
        (ArchitecturePattern.SAAS, 'medium'),
        (ArchitecturePattern.GAMING, 'large'),
        (ArchitecturePattern.DATA_PIPELINE, 'medium'),
        (ArchitecturePattern.MICROSERVICES, 'large'),
        (ArchitecturePattern.SERVERLESS, 'small'),
        (ArchitecturePattern.ML_PLATFORM, 'large'),
        (ArchitecturePattern.MEDIA_STREAMING, 'xlarge'),
    ]
    
    results = []
    
    for pattern, complexity in patterns:
        print(f"\n🔨 Generating {pattern.value} ({complexity})...")
        
        generator = ArchitectureGenerator(pattern, complexity)
        arch = generator.generate()
        
        filename = f"{output_dir}/{pattern.value}_{complexity}.json"
        with open(filename, 'w') as f:
            json.dump(arch, f, indent=2)
        
        print(f"   ✅ Created: {filename}")
        print(f"   📊 Services: {arch['metadata']['total_services']}")
        print(f"   💰 Monthly Cost: ${arch['metadata']['total_cost_monthly']:,.2f}")
        
        results.append({
            'pattern': pattern.value,
            'complexity': complexity,
            'file': filename,
            'services': arch['metadata']['total_services'],
            'cost': arch['metadata']['total_cost_monthly']
        })
    
    # Create summary
    summary_file = f"{output_dir}/architecture_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Generated {len(results)} architectures")
    print(f"📄 Summary: {summary_file}")
    
    return results

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        pattern_name = sys.argv[1]
        complexity = sys.argv[2] if len(sys.argv) > 2 else 'medium'
        
        try:
            pattern = ArchitecturePattern(pattern_name)
            generator = ArchitectureGenerator(pattern, complexity)
            arch = generator.generate()
            
            filename = f"{pattern.value}_{complexity}.json"
            with open(filename, 'w') as f:
                json.dump(arch, f, indent=2)
            
            print(f"✅ Generated: {filename}")
            print(f"   Services: {arch['metadata']['total_services']}")
            print(f"   Cost: ${arch['metadata']['total_cost_monthly']:,.2f}")
        
        except ValueError:
            print(f"❌ Unknown pattern: {pattern_name}")
            print(f"Available patterns: {[p.value for p in ArchitecturePattern]}")
    else:
        # Generate all patterns
        generate_all_patterns()