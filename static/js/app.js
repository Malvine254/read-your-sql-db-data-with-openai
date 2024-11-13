$(document).ready(function() {
    const chatWindow = $('#chatWindow');
    const inputField = $('#inputMessage');
    const sendButton = $('#sendButton');

    // Trigger sendMessage when the send button is clicked
    sendButton.click(sendMessage);

    // Trigger sendMessage when pressing Enter in the input field
    inputField.keypress(function(e) {
        if (e.which === 13) {  // Enter key pressed
            sendMessage();
        }
    });

    function sendMessage() {
        const inputMessage = inputField.val().trim();
        if (!inputMessage) return;  // Do nothing if the message is empty

        // Append the user's message to the chat window
        const userMessage = `<div class="message user"><p>${inputMessage}</p></div>`;
        chatWindow.append(userMessage);
        chatWindow.scrollTop(chatWindow[0].scrollHeight);

        // Clear the input field
        inputField.val('');

        // Send the request to the Flask backend
        $.ajax({
            url: '/ask',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ message: inputMessage }),

            beforeSend: function() {
                // Show a typing indicator
                const typingIndicator = `
                    <div id="typing-indicator" class="message system">
                        <img src="https://media.tenor.com/6DR9HRfOFu8AAAAM/typing-loading.gif" alt="AI is typing..." style="width: 100px; height: auto;" />
                    </div>
                `;
                chatWindow.append(typingIndicator);
                chatWindow.scrollTop(chatWindow[0].scrollHeight);
            },

            success: function(data) {
                // Remove the typing indicator
                console.log(data)
                $('#typing-indicator').fadeOut(100, function() {
                    $(this).remove();
                });
                

                // Display the summary message from the AI response
                if (data.summary) {
                    function checkIfEmpty (){
                        if(data.chart_image ===""){
                            return '';
                        }else{
                            return  `<img class="img-fluid" src="data:image/png;base64,${data.chart_image}"></img>`
                        }
                    }
                    const summaryMessage = `
                        <div class="message system">
                            <p> ${data.summary}
                           
                            ${checkIfEmpty ()}
                            
                            </p>
                            <small>AI-generated summary</small>
                        </div>
                    `;
                    chatWindow.append(summaryMessage);
                }

                // Check if the response contains a list of results
                if (Array.isArray(data.response) && data.response.length > 0) {
                    // Display each result in a formatted manner
                    data.response.forEach(record => {
                        const recordMessage = `
                            <div class="message system">

                                <p>${formatRecord(record)}</p>
                                <small>AI-generated database result</small>
                            </div>
                        `;
                        chatWindow.append(recordMessage);
                    });
                }

                chatWindow.scrollTop(chatWindow[0].scrollHeight);
            },

            error: function(err) {
                // Remove the typing indicator in case of an error
                $('#typing-indicator').fadeOut(100, function() {
                    $(this).remove();
                });

                console.error("Error: ", err);
                const errorMessage = `
                    <div class="message system">
                        <p>There was an error processing your request. Please try again.</p>
                    </div>
                `;
                chatWindow.append(errorMessage);
                chatWindow.scrollTop(chatWindow[0].scrollHeight);
            }
        });
    }

    // Helper function to format each record as a string
    function formatRecord(record) {
        return Object.entries(record).map(([key, value]) => `<strong>${key}:</strong> ${value}`).join("<br>");
    }
});
