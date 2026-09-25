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
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '用户ID',
  `username` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户名',
  `email` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '邮箱',
  `hashed_password` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '哈希密码',
  `status` tinyint(1) DEFAULT '1' COMMENT '状态: True=活跃, False=非活跃',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`),
  KEY `idx_username` (`username`),
  KEY `idx_email` (`email`),
  KEY `idx_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'oyx','oyx@163.com','$2b$12$g9gggx/BUHARrbiJn7F7I.Wc7VoB46GLKdDPEc1cFeA07Rfv2UEJe',1,'2026-01-09 02:16:07','2026-01-14 07:59:09'),(2,'wyq','wyq@qq.com','$2b$12$CFObfp.OPaUoGAiKZ2m3AO6mcdx3V.6puq5L8.kKvI8CKraKTQgxu',1,'2026-01-12 01:52:46','2026-01-14 07:59:09'),(3,'zqy','zqy@163.com','$2b$12$U4HIsx5WeCyhau8GYWjQOeJa.E/g/W8KrmhqDIHSrE5GtrgCTsz/6',1,'2026-01-14 05:10:30','2026-01-14 07:59:09'),(4,'ljm','lj@163.com','$2b$12$2KFSegTvAqcT4WzMKE/vPOQD7KMOVzJEXgSTFFCQ8ZF.4mHRI9mH.',1,'2026-01-14 05:12:24','2026-01-14 07:59:09'),(8,'test','test@qq.com','$2b$12$78CFjWf9oFKrKqVjHZAvhO7e4mFXxZ38mN0QGIyeqI1danbk3XW9G',1,'2026-01-15 05:08:15','2026-01-15 05:08:15'),(9,'123','123@163.com','$2b$12$ck9pjB.wxOrpUmbZOLF0z.3rfbpuggtGTd1G2qkDxe9CHEx7XvRhe',1,'2026-01-16 02:47:18','2026-01-16 02:47:18'),(10,'145','145@163.com','$2b$12$wlD7mIHfn9dWmRr2xHh8re0uLaRLQ2A5iSraKD0sfFXxrK2j1nLWW',1,'2026-01-16 03:10:30','2026-01-16 03:10:30');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
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
