import 'package:flutter/material.dart';

class SubscriptionPackagesScreen extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('ZIMBOT Premium'),
        backgroundColor: Colors.green[800],
      ),
      body: SingleChildScrollView(
        padding: EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Select Your Package',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 8),
            Text(
              'Empower your farming with data-driven market intelligence.',
              style: TextStyle(color: Colors.grey[600]),
            ),
            SizedBox(height: 24),
            
            // Seed Package
            _buildPackageCard(
              context,
              title: 'Seed Package',
              price: '\$3/month',
              updates: '1 update per week',
              features: ['Friday Market Summary', 'Basic Price Alerts'],
              color: Colors.green[100]!,
              icon: Icons.eco,
              planId: 'seed',
            ),
            
            SizedBox(height: 16),
            
            // Growth Package
            _buildPackageCard(
              context,
              title: 'Growth Package',
              price: '\$5/month',
              updates: '2 updates per week',
              features: ['Monday & Friday Updates', 'Priority Price Alerts', 'Market Trends'],
              color: Colors.green[200]!,
              icon: Icons.trending_up,
              isPopular: true,
              planId: 'growth',
            ),
            
            SizedBox(height: 16),
            
            // Harvest Package
            _buildPackageCard(
              context,
              title: 'Harvest Package',
              price: '\$10/month',
              updates: '3 updates per week',
              features: ['Mon, Wed, Fri Updates', 'Deep Market Intel', 'Actionable Advice', 'Direct Support'],
              color: Colors.green[400]!,
              icon: Icons.agriculture,
              planId: 'harvest',
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPackageCard(
    BuildContext context, {
    required String title,
    required String price,
    required String updates,
    required List<String> features,
    required Color color,
    required IconData icon,
    bool isPopular = false,
    required String planId,
  }) {
    return Card(
      elevation: 4,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Stack(
        children: [
          Padding(
            padding: const EdgeInsets.all(20.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Icon(icon, size: 40, color: Colors.green[800]),
                    Text(
                      price,
                      style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Colors.green[900]),
                    ),
                  ],
                ),
                SizedBox(height: 12),
                Text(
                  title,
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                ),
                Text(
                  updates,
                  style: TextStyle(color: Colors.green[700], fontWeight: FontWeight.w600),
                ),
                Divider(height: 24),
                ...features.map((f) => Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4.0),
                  child: Row(
                    children: [
                      Icon(Icons.check_circle, size: 18, color: Colors.green),
                      SizedBox(width: 8),
                      Text(f),
                    ],
                  ),
                )).toList(),
                SizedBox(height: 20),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: () {
                      // Logic to trigger Pesapal Checkout
                      print('Initiating payment for $planId');
                    },
                    child: Text('Subscribe Now'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.green[800],
                      foregroundColor: Colors.white,
                      padding: EdgeInsets.symmetric(vertical: 12),
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (isPopular)
            Positioned(
              top: 0,
              right: 0,
              child: Container(
                padding: EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.orange,
                  borderRadius: BorderRadius.only(
                    topRight: Radius.circular(12),
                    bottomLeft: Radius.circular(12),
                  ),
                ),
                child: Text(
                  'MOST POPULAR',
                  style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
