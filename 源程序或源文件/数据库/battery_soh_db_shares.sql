-- MySQL dump 10.13  Distrib 8.0.33, for Win64 (x86_64)
--
-- Host: localhost    Database: battery_soh_db
-- ------------------------------------------------------
-- Server version	8.0.33

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `shares`
--

DROP TABLE IF EXISTS `shares`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `shares` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '分享ID',
  `resource_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '资源类型: model/dataset/prediction/training',
  `resource_id` int NOT NULL COMMENT '资源ID',
  `owner_id` int NOT NULL COMMENT '资源所有者ID',
  `shared_with_user_id` int DEFAULT NULL COMMENT '被分享的用户ID（NULL表示公开分享）',
  `permission` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'read' COMMENT '权限: read=只读, write=读写',
  `notes` text COLLATE utf8mb4_unicode_ci COMMENT '分享备注',
  `expires_at` timestamp NULL DEFAULT NULL COMMENT '分享过期时间',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `is_active` tinyint(1) NOT NULL DEFAULT '1' COMMENT '是否激活',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_share_resource_user` (`resource_type`,`resource_id`,`shared_with_user_id`,`owner_id`),
  KEY `idx_resource` (`resource_type`,`resource_id`),
  KEY `idx_owner_id` (`owner_id`),
  KEY `idx_shared_with_user_id` (`shared_with_user_id`),
  KEY `idx_is_active` (`is_active`),
  KEY `idx_created_at` (`created_at`),
  CONSTRAINT `shares_ibfk_1` FOREIGN KEY (`owner_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `shares_ibfk_2` FOREIGN KEY (`shared_with_user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=30 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='资源共享表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `shares`
--

LOCK TABLES `shares` WRITE;
/*!40000 ALTER TABLE `shares` DISABLE KEYS */;
INSERT INTO `shares` VALUES (2,'model',58,1,4,'write','',NULL,'2026-01-15 02:20:06','2026-01-15 02:20:06',1),(3,'model',59,1,4,'write','',NULL,'2026-01-15 02:20:06','2026-01-15 02:20:06',1),(4,'model',61,1,4,'write','',NULL,'2026-01-15 02:20:06','2026-01-15 02:20:06',1),(5,'model',62,1,4,'write','',NULL,'2026-01-15 02:20:06','2026-01-15 02:20:06',1),(6,'model',63,1,4,'write','',NULL,'2026-01-15 02:20:06','2026-01-15 02:20:06',1),(7,'model',64,1,4,'write','',NULL,'2026-01-15 02:20:06','2026-01-15 02:20:06',1),(8,'model',68,1,4,'write','',NULL,'2026-01-15 02:20:06','2026-01-15 02:20:06',1),(9,'model',69,1,4,'write','',NULL,'2026-01-15 02:20:06','2026-01-15 02:20:06',1),(10,'model',47,1,4,'write','',NULL,'2026-01-15 02:20:06','2026-01-15 02:20:06',1),(11,'model',72,4,2,'read','',NULL,'2026-01-15 03:10:25','2026-01-15 03:10:25',1),(12,'model',72,4,1,'read','',NULL,'2026-01-15 03:10:25','2026-01-15 03:10:25',1),(13,'model',72,4,3,'read','',NULL,'2026-01-15 03:10:25','2026-01-15 03:10:25',1),(16,'model',70,4,2,'read','',NULL,'2026-01-15 03:10:25','2026-01-15 03:10:25',1),(17,'model',70,4,1,'read','',NULL,'2026-01-15 03:10:25','2026-01-15 03:10:25',1),(18,'model',70,4,3,'read','',NULL,'2026-01-15 03:10:25','2026-01-15 03:10:25',1),(21,'model',69,1,2,'read','',NULL,'2026-01-15 05:43:21','2026-01-15 05:43:21',1),(22,'model',68,1,2,'read','',NULL,'2026-01-15 05:43:21','2026-01-15 05:43:21',1),(23,'model',45,1,4,'write','',NULL,'2026-01-16 03:16:36','2026-01-16 03:16:36',1),(24,'model',45,1,2,'write','',NULL,'2026-01-16 03:16:36','2026-01-16 03:16:36',1),(25,'model',47,1,2,'write','',NULL,'2026-01-16 03:16:36','2026-01-16 03:16:36',1),(26,'model',48,1,4,'write','',NULL,'2026-01-16 03:16:36','2026-01-16 03:16:36',1),(27,'model',48,1,2,'write','',NULL,'2026-01-16 03:16:36','2026-01-16 03:16:36',1),(28,'model',49,1,4,'write','',NULL,'2026-01-16 03:16:36','2026-01-16 03:16:36',1),(29,'model',49,1,2,'write','',NULL,'2026-01-16 03:16:36','2026-01-16 03:16:36',1);
/*!40000 ALTER TABLE `shares` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-01-16 12:07:45
