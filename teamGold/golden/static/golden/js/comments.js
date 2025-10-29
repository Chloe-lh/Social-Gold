document.addEventListener("DOMContentLoaded", function(){
    const modal = document.getElementById("comment-modal");
    const closeBtn = document.querySelector(".close-btn");
    const commentList = document.getElementById("comment-list");
    var entryComments = JSON.parse(document.getElementById('entry-comments').textContent);


    // Attach click event to all comment buttons
    document.querySelectorAll('.comment-btn').forEach(btn => {
        btn.addEventListener("click", function() {
            modal.showModal();
            document.getElementById('modalEntryId').value = this.dataset.entryId;

            // Get comments for this entry
            const entryId = this.dataset.entryId;
            const comments = entryComments[entryId] || [];
            commentList.innerHTML = "";
            if (comments.length === 0) {
                commentList.innerHTML = "<div>No comments yet.</div>";
            } else {
                comments.forEach(c => {
                    // uses fields from Comment Serializer
                    commentList.innerHTML += `
                        <div class="single-comment">
                            <strong>${c.author_username}</strong> <span>${new Date(c.published).toLocaleString()}</span>
                            <p>${c.content}</p>
                        </div>
                    `;
                });
            }
        });
    });

    // Close modal
    if (closeBtn) {
        closeBtn.addEventListener("click", () => {
            modal.close()
        });
    }

       // Close modal when clicking outside modal
    window.onclick = function(event) {
    if (modal.open && event.target === modal) {
        modal.close();
    }
};

    // AJAX submit comment form
    document.getElementById('commentForm').addEventListener('submit', function(event){
        event.preventDefault();
        const formData = new FormData(this);
        // fetch - Javascript API used to send HTTP/AJAX requests from browser
        //  to Django API endpoints (/api/Comment/<entry_id>)
        // this = form element
        // action = URL
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
                window.location.reload();
                modal.close();
            }else{
                alert(data.error || "Failed to add comment");
            }
        });
    });
});