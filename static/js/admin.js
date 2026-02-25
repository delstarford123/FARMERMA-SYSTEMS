/* =========================================
   ADMIN PORTAL TOOLS
   ========================================= */

document.addEventListener("DOMContentLoaded", function() {
    
    // 1. Table Search Filter
    const searchInput = document.getElementById('adminTableSearch');
    const tableBody = document.getElementById('adminTableBody');

    if (searchInput && tableBody) {
        searchInput.addEventListener('keyup', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const rows = tableBody.getElementsByTagName('tr');

            // Loop through all table rows, and hide those who don't match the search query
            Array.from(rows).forEach(function(row) {
                const textContent = row.textContent.toLowerCase();
                if (textContent.includes(searchTerm)) {
                    row.style.display = ""; // Show row
                } else {
                    row.style.display = "none"; // Hide row
                }
            });
        });
    }

    // 2. Confirm Deletion Prompts
    const deleteButtons = document.querySelectorAll('.btn-delete-confirm');
    deleteButtons.forEach(function(btn) {
        btn.addEventListener('click', function(e) {
            if (!confirm("Are you sure you want to perform this deletion? This action cannot be undone.")) {
                e.preventDefault(); // Stop the form submission or link click if they hit cancel
            }
        });
    });
});