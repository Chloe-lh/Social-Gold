document.addEventListener("DOMContentLoaded", function(){
    const modal = document.getElementById("commentModal");
    const closeBtn = document.querySelector(".close-btn");
    const commentList = document.getElementById("comment-list");
    var entryComments = JSON.parse(document.getElementById('entry-comments').textContent);
    // Attach click event to all comment buttons
    document.querySelectorAll('.comment-btn').forEach(btn => {
        btn.addEventListener("click", function() {
            modal.style.display = "block";
            document.getElementById('modalEntryId').value = this.dataset.entryId;

            // Get comments for this entry
            const entryId = this.dataset.entryId;
            const comments = entryComments[entryId] || [];
            commentList.innerHTML = "";
            if (comments.length === 0) {
                commentList.innerHTML = "<div>No comments yet.</div>";
            } else {
                comments.forEach(c => {
                    commentList.innerHTML += `
                        <div class="single-comment">
                            <strong>${c.author}</strong> <span>${c.published}</span>
                            <p>${c.comment}</p>
                        </div>
                    `;
                });
            }
        });
    });

    // Close modal
    if (closeBtn) {
        closeBtn.addEventListener("click", () => {
            modal.style.display = "none";
        });
    }

    // Close modal when clicking outside
    window.onclick = function(event) {
        if (event.target == modal) {
            modal.style.display = "none";
        }
    };

    // AJAX submit comment form
    document.getElementById('commentForm').addEventListener('submit', function(event){
        event.preventDefault();
        const formData = new FormData(this);
        fetch(this.action, {
            method: "POST",
            headers: {
                "X-CSRFToken": formData.get('csrfmiddlewaretoken'),
            },
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if(data.success){
                modal.style.display = 'none';
                location.reload();
            }else{
                alert(data.error || "Failed to add comment");
            }
        });
    });
});