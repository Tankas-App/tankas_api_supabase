class PointsCalculator:
    """Calculate points for issues and volunteers"""
    
    # Base points for each difficulty level
    DIFFICULTY_POINTS = {
        "easy": 10,
        "medium": 20,
        "hard": 30
    }
    
    # Multiplier for each priority level
    PRIORITY_MULTIPLIER = {
        "low": 1.0,
        "medium": 1.5,
        "high": 2.0
    }
    
    @staticmethod
    def calculate_issue_points(difficulty: str, priority: str) -> int:
        """
        Calculate total points for an issue
        
        Formula: base_points × priority_multiplier = total_points
        
        Examples:
        - easy + low priority = 10 × 1.0 = 10 points
        - medium + medium priority = 20 × 1.5 = 30 points
        - hard + high priority = 30 × 2.0 = 60 points
        
        Args:
            difficulty: "easy", "medium", or "hard"
            priority: "low", "medium", or "high"
            
        Returns:
            Total points for this issue
            
        Raises:
            ValueError: If difficulty or priority is invalid
        """
        # Validate difficulty
        if difficulty.lower() not in PointsCalculator.DIFFICULTY_POINTS:
            raise ValueError(f"Invalid difficulty: {difficulty}. Must be easy, medium, or hard")
        
        # Validate priority
        if priority.lower() not in PointsCalculator.PRIORITY_MULTIPLIER:
            raise ValueError(f"Invalid priority: {priority}. Must be low, medium, or high")
        
        # Calculate points
        base_points = PointsCalculator.DIFFICULTY_POINTS[difficulty.lower()]
        multiplier = PointsCalculator.PRIORITY_MULTIPLIER[priority.lower()]
        total_points = int(base_points * multiplier)
        
        return total_points
    
    @staticmethod
    def distribute_points_equally(total_points: int, num_volunteers: int) -> int:
        """
        Distribute points equally among volunteers
        
        Args:
            total_points: Total points available for the issue
            num_volunteers: Number of volunteers who completed the work
            
        Returns:
            Points per volunteer (rounded down)
            
        Raises:
            ValueError: If inputs are invalid
        """
        if total_points < 0:
            raise ValueError("Total points cannot be negative")
        
        if num_volunteers <= 0:
            raise ValueError("Number of volunteers must be greater than 0")
        
        points_per_volunteer = total_points // num_volunteers  # Integer division
        
        return points_per_volunteer
    
    @staticmethod
    def distribute_points_with_leader(total_points: int, num_volunteers: int, leader_id: str = None) -> dict:
        """
        Distribute points equally among volunteers, with leader getting remainder as bonus
        
        Example:
        - 65 points ÷ 3 volunteers
        - Each volunteer gets: 65 // 3 = 21 points
        - Remainder: 65 % 3 = 2 points
        - Leader gets: 21 + 2 = 23 points
        
        Args:
            total_points: Total points available for the issue
            num_volunteers: Number of volunteers who completed the work
            leader_id: Optional leader identifier (for tracking)
            
        Returns:
            Dictionary with:
            - points_per_volunteer: Points each regular volunteer gets
            - leader_bonus: Remainder points for leader
            - leader_total: Total points for leader
            - distribution: Breakdown of who gets what
        """
        if total_points < 0:
            raise ValueError("Total points cannot be negative")
        
        if num_volunteers <= 0:
            raise ValueError("Number of volunteers must be greater than 0")
        
        points_per_volunteer = total_points // num_volunteers
        remainder = total_points % num_volunteers
        leader_total = points_per_volunteer + remainder
        
        return {
            "points_per_volunteer": points_per_volunteer,
            "leader_bonus": remainder,
            "leader_total": leader_total,
            "distribution": {
                "regular_volunteers": {
                    "count": num_volunteers - 1,  # Excluding leader
                    "points_each": points_per_volunteer
                },
                "leader": {
                    "id": leader_id,
                    "points": leader_total
                },
                "total_distributed": (points_per_volunteer * (num_volunteers - 1)) + leader_total
            }
        }
    
    @staticmethod
    def calculate_leader_bonus(base_points: int, bonus_percentage: float = 0.1) -> int:
        """
        Calculate bonus points for group leader
        
        Leaders get a bonus for verifying and managing the group.
        Default: 10% of base points
        
        Args:
            base_points: Points the leader earned for doing the cleanup
            bonus_percentage: What percentage bonus to add (default 10%)
            
        Returns:
            Total points for leader (base + bonus)
        """
        bonus = int(base_points * bonus_percentage)
        return base_points + bonus
    
    @staticmethod
    def get_badge_tier(total_points: int) -> str:
        """
        Determine badge tier based on total accumulated points
        
        Args:
            total_points: User's total lifetime points
            
        Returns:
            Badge tier: "bronze", "silver", or "gold"
        """
        if total_points >= 501:
            return "gold"
        elif total_points >= 101:
            return "silver"
        else:
            return "bronze"
    
    @staticmethod
    def calculate_points_to_next_tier(total_points: int) -> int:
        """
        Calculate how many more points needed to reach next tier
        
        Args:
            total_points: User's current total points
            
        Returns:
            Points needed to reach next tier
        """
        current_tier = PointsCalculator.get_badge_tier(total_points)
        
        if current_tier == "bronze":
            return 101 - total_points
        elif current_tier == "silver":
            return 501 - total_points
        else:  # gold
            return 0  # Already at max tier