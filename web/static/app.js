document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    const gameGrid = document.getElementById('game-grid');
    const libraryTitle = document.getElementById('library-title');
    const userSwitcherButton = document.getElementById('user-switcher-button');
    const userSwitcherDropdown = document.getElementById('user-switcher-dropdown');
    let selectedUserIds = []; // To store selected user IDs
    const nameFilterInput = document.getElementById('name-filter');
    const platformFilter = document.getElementById('platform-filter');
    const playersFilter = document.getElementById('players-filter');
    const gamepassFilter = document.getElementById('gamepass-filter');
    
    let allGames = [];
    let currentDiscordId = INITIAL_DISCORD_ID;
    let viewerId = VIEWER_ID;

    // --- Initial Load ---
    function initialize() {
        loadUsers();
        // Initialize selectedUserIds with the initial user
        selectedUserIds = [INITIAL_DISCORD_ID];
        loadUserLibrary(selectedUserIds);
    }

    function loadUsers() {
        fetch('/api/users')
            .then(res => res.json())
            .then(users => {
                users.sort((a, b) => a.username.localeCompare(b.username));
                userSwitcherDropdown.innerHTML = ''; // Clear previous content
                users.forEach(user => {
                    const userDiv = document.createElement('div');
                    userDiv.className = 'dropdown-item';
                    userDiv.innerHTML = `
                        <input type="checkbox" id="user-${user.discord_id}" value="${user.discord_id}" data-username="${user.username}">
                        <label for="user-${user.discord_id}">${user.username}</label>
                    `;
                    userSwitcherDropdown.appendChild(userDiv);

                    const checkbox = userDiv.querySelector(`#user-${user.discord_id}`);
                    const label = userDiv.querySelector(`label[for="user-${user.discord_id}"]`);

                    // Set initial checked state
                    if (user.discord_id === INITIAL_DISCORD_ID) {
                        checkbox.checked = true;
                    }

                    // Event listener for checkbox change
                    checkbox.addEventListener('change', () => {
                        if (checkbox.checked) {
                            selectedUserIds.push(user.discord_id);
                        } else {
                            selectedUserIds = selectedUserIds.filter(id => id !== user.discord_id);
                        }
                        loadUserLibrary(selectedUserIds);
                    });

                    // Event listener for label click (single-select behavior)
                    label.addEventListener('click', (event) => {
                        event.preventDefault(); // Prevent checkbox default toggle
                        // If this user is already the only one selected, do nothing
                        if (selectedUserIds.length === 1 && selectedUserIds[0] === user.discord_id) {
                            return;
                        }

                        // Clear all other checkboxes and select only this one
                        userSwitcherDropdown.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                            cb.checked = (cb.value === user.discord_id);
                        });
                        selectedUserIds = [user.discord_id];
                        loadUserLibrary(selectedUserIds);
                    });
                });
            });
    }

    let isCurrentUserLibrary = false;

    function loadUserLibrary(discordIds) {
        // Update currentDiscordId to the first ID if only one is selected, for backward compatibility
        currentDiscordId = discordIds.length === 1 ? discordIds[0] : null;
        isCurrentUserLibrary = (discordIds.length === 1 && discordIds[0] === viewerId);

        // Update library title based on selected users
        if (discordIds.length === 0) {
            libraryTitle.textContent = 'Select Users';
            allGames = [];
            renderGames([]);
            return;
        } else if (discordIds.length === 1) {
            const selectedUser = userSwitcherDropdown.querySelector(`input[value="${discordIds[0]}"]`);
            if (selectedUser) {
                libraryTitle.textContent = `${selectedUser.dataset.username}'s Library`;
            }
        } else {
            const selectedUsernames = Array.from(userSwitcherDropdown.querySelectorAll('input[type="checkbox"]:checked'))
                                        .map(cb => cb.dataset.username);
            libraryTitle.textContent = `Games common to ${selectedUsernames.join(' & ')}`;
        }

        const userIdsParam = discordIds.join(',');
        // Update the button text
        if (discordIds.length === 0) {
            userSwitcherButton.textContent = 'Select Users';
        } else {
            const selectedUsernames = Array.from(userSwitcherDropdown.querySelectorAll('input[type="checkbox"]'))
                                        .filter(cb => discordIds.includes(cb.value))
                                        .map(cb => cb.dataset.username);
            userSwitcherButton.textContent = selectedUsernames.join(', ');
        }
        fetch(`/api/games?user_ids=${userIdsParam}`)
            .then(res => res.json())
            .then(games => {
                allGames = games.sort((a, b) => a.name.localeCompare(b.name));
                populateFilters(allGames);
                applyFilters();
            });
    }

    // --- Event Listeners for Filters ---
    userSwitcherButton.addEventListener('click', () => {
        userSwitcherDropdown.classList.toggle('show');
    });

    // Close the dropdown if the user clicks outside of it
    window.addEventListener('click', (event) => {
        if (!event.target.matches('#user-switcher-button') && !event.target.closest('.user-switcher-container')) {
            if (userSwitcherDropdown.classList.contains('show')) {
                userSwitcherDropdown.classList.remove('show');
            }
        }
    });

    // Existing filter event listeners
    [nameFilterInput, platformFilter, playersFilter, gamepassFilter].forEach(el => el.addEventListener('input', applyFilters));

    // --- Filtering Logic ---
    function populateFilters(games) {
        const allSources = new Set();
        games.forEach(game => {
            game.sources.forEach(source => {
                let standardizedSource = source;
                if (source === 'Game_Pass') {
                    standardizedSource = 'Game Pass';
                } else if (source === 'Pc') {
                    standardizedSource = 'PC';
                }
                allSources.add(standardizedSource);
            });
        });
        const platforms = Array.from(allSources).sort();
        platformFilter.innerHTML = '<option value="">All Platforms</option>';
        platforms.forEach(p => platformFilter.add(new Option(p, p)));

        const players = [...new Set(games.map(g => g.max_players).filter(Boolean))].sort((a,b) => a - b);
        playersFilter.innerHTML = '<option value="">Any Players</option>';
        for(let i = 1; i <= Math.max(...players, 8); i++) {
             playersFilter.add(new Option(`${i}+ Players`, i));
        }
    }

    function applyFilters() {
        const nameQuery = nameFilterInput.value.toLowerCase();
        const platformQuery = platformFilter.value;
        const playersQuery = parseInt(playersFilter.value, 10);
        const gamepassQuery = gamepassFilter.value;

        const filteredGames = allGames.filter(game => {
            const nameMatch = game.name.toLowerCase().includes(nameQuery);
            // Check if the game's sources include the selected platformQuery
            const platformMatch = !platformQuery || game.sources.map(s => {
                if (s === 'Game_Pass') return 'Game Pass';
                if (s === 'Pc') return 'PC';
                return s;
            }).includes(platformQuery);
            const playersMatch = !playersQuery || (game.max_players >= playersQuery);
            const gamepassMatch = 
                gamepassQuery === 'include' ? true :
                gamepassQuery === 'only' ? game.is_game_pass :
                gamepassQuery === 'exclude' ? !game.is_game_pass :
                true;
            return nameMatch && platformMatch && playersMatch && gamepassMatch;
        });
        renderGames(filteredGames);
    }

    // --- Rendering and Card Flip Logic ---
    function renderGames(games) {
        gameGrid.innerHTML = '';
        if (games.length === 0) {
            gameGrid.innerHTML = '<p>No games found with the current filters.</p>';
            return;
        }

        games.forEach(game => {
            const cardContainer = document.createElement('div');
            cardContainer.className = 'game-card';
            cardContainer.dataset.gameId = game.id;

            // --- Define the image URL waterfall ---
            const placeholderUrl = `/api/placeholder/${encodeURIComponent(game.name)}`;
            const imageUrl = game.cover_url || placeholderUrl;

            // --- Build the card's inner HTML ---
            cardContainer.innerHTML = `
                <div class="game-card-inner">
                    <div class="game-card-front" style="background-image: url('${imageUrl}');">
                        <div class="game-card-title-banner">${game.name}</div>
                        ${isCurrentUserLibrary ? `
                            <div class="game-card-actions-overlay">
                                <button class="action-button like-button ${game.liked ? 'active' : ''}" data-game-id="${game.id}">❤</button>
                                <button class="action-button dislike-button ${game.disliked ? 'active' : ''}" data-game-id="${game.id}">✕</button>
                            </div>
                        ` : ''}
                    </div>
                    ${game.is_game_pass ? '<div class="game-pass-overlay"></div>' : ''}
                    <div class="game-card-back">
                        <p>Loading...</p>
                        ${isCurrentUserLibrary ? `
                            <div class="game-management-buttons">
                                <button class="toggle-installed-button" data-game-id="${game.id}" ${game.sources.length === 0 ? 'disabled' : ''}>
                                    ${game.is_installed ? 'Uninstalled' : 'Installed'}
                                </button>
                                <button class="delete-game-button" data-game-id="${game.id}">Delete</button>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;

            cardContainer.addEventListener('click', (event) => {
                // Only flip the card if the click is not on an action button
                if (!event.target.classList.contains('action-button') &&
                    !event.target.classList.contains('toggle-installed-button') &&
                    !event.target.classList.contains('toggle-owned-button')) {
                    handleCardClick(cardContainer, game);
                }
            });

            if (isCurrentUserLibrary) {
                const toggleInstalledButton = cardContainer.querySelector('.toggle-installed-button');
                if (toggleInstalledButton) {
                    toggleInstalledButton.addEventListener('click', (event) => {
                        event.stopPropagation(); // Prevent card flip
                        handleToggleInstalled(game.id);
                    });
                }

                const likeButton = cardContainer.querySelector('.like-button');
                if (likeButton) {
                    likeButton.addEventListener('click', (event) => {
                        event.stopPropagation(); // Prevent card flip
                        handleLikeGame(game.id, likeButton, cardContainer.querySelector('.dislike-button'));
                    });
                }

                const dislikeButton = cardContainer.querySelector('.dislike-button');
                if (dislikeButton) {
                    dislikeButton.addEventListener('click', (event) => {
                        event.stopPropagation(); // Prevent card flip
                        handleDislikeGame(game.id, dislikeButton, cardContainer.querySelector('.like-button'));
                    });
                }

                const deleteButton = cardContainer.querySelector('.delete-game-button');
                if (deleteButton) {
                    deleteButton.addEventListener('click', (event) => {
                        event.stopPropagation(); // Prevent card flip
                        handleDeleteGame(game.id, game.sources);
                    });
                }
            }

            gameGrid.appendChild(cardContainer);
        });
    }

    function handleCardClick(cardElement, game) {
        const isFlipped = cardElement.classList.contains('flipped');

        // Un-flip any other card that is already flipped
        document.querySelectorAll('.game-card.flipped').forEach(flippedCard => {
            if (flippedCard !== cardElement) {
                flippedCard.classList.remove('flipped');
            }
        });

        // Flip or un-flip the clicked card
        cardElement.classList.toggle('flipped');

        if (!isFlipped) {
            const backOfCard = cardElement.querySelector('.game-card-back');
            backOfCard.innerHTML = '<p>Loading...</p>';

            // Immediately populate with available game data
            const sourcesHtml = game.sources && game.sources.length > 0
                ? `<h4>Sources:</h4><ul>${game.sources.map(s => `<li>${s}</li>`).join('')}</ul>`
                : '';

            backOfCard.innerHTML = `
                <div class="card-back-title">${game.name}</div>
                <div class="card-back-content">
                    <p><strong>Metacritic:</strong> ${game.metacritic || "Not available"}</p>
                    <p>${game.description || "No summary available."}</p>
                    ${sourcesHtml}
                    <div id="owners-list"></div> <!-- Placeholder for owners -->
                </div>
                ${isCurrentUserLibrary ? `
                    <div class="game-management-buttons">
                        <button class="toggle-installed-button" data-game-id="${game.id}" ${game.sources.length === 0 ? 'disabled' : ''}>
                            ${game.is_installed ? 'Uninstalled' : 'Installed'}
                        </button>
                        <button class="delete-game-button" data-game-id="${game.id}">Delete</button>
                    </div>
                ` : ''}
            `;

            // Fetch owners separately
            fetch(`/api/game_details/${game.id}`)
                .then(res => res.json())
                .then(details => {
                    const otherOwners = details.owners.filter(o => o.username !== libraryTitle.textContent.replace("'s Library", ""));
                    const ownersHtml = otherOwners.length > 0 
                        ? `<h4>Also Owned By:</h4><ul>${otherOwners.map(o => `<li>${o.username}</li>`).join('')}</ul>`
                        : '';
                    cardElement.querySelector('#owners-list').innerHTML = ownersHtml;

                    // Re-attach event listeners for the newly rendered buttons on the back of the card
                    if (isCurrentUserLibrary) {
                        const toggleInstalledButton = backOfCard.querySelector('.toggle-installed-button');
                        if (toggleInstalledButton) {
                            toggleInstalledButton.addEventListener('click', (event) => {
                                event.stopPropagation(); // Prevent card flip
                                handleToggleInstalled(game.id);
                            });
                        }

                        const deleteButton = backOfCard.querySelector('.delete-game-button');
                        if (deleteButton) {
                            deleteButton.addEventListener('click', (event) => {
                                event.stopPropagation(); // Prevent card flip
                                handleDeleteGame(game.id, game.sources);
                            });
                        }
                    }
                });
        }
    }

    // --- New Game Management Functions ---

    // Delete Game Modal Elements
    const deleteConfirmModal = document.getElementById('deleteConfirmModal');
    const deleteConfirmMessage = document.getElementById('deleteConfirmMessage');
    const deleteSourceSelect = document.getElementById('deleteSourceSelect');
    const confirmDeleteButton = document.getElementById('confirmDeleteButton');
    const cancelDeleteButton = document.getElementById('cancelDeleteButton');
    const deleteModalCloseButton = deleteConfirmModal.querySelector('.close-button');

    // Toast Notification Element
    const toastElement = document.getElementById('toast');

    let gameToDelete = null; // To store the game ID and sources for deletion

    function showToast(message, isError = false) {
        toastElement.textContent = message;
        toastElement.className = 'toast show';
        if (isError) {
            toastElement.style.backgroundColor = '#f44336'; // Red for error
        } else {
            toastElement.style.backgroundColor = '#333'; // Default for success/info
        }
        setTimeout(() => {
            toastElement.className = toastElement.className.replace("show", "");
        }, 3000); // Hide after 3 seconds
    }

    async function handleDeleteGame(gameId, sources) {
        console.log('Delete button clicked for game:', gameId, 'with sources:', sources);
        gameToDelete = { gameId, sources };
        
        // Prioritize Steam if it exists and there are other sources
        const steamSource = sources.find(s => s === 'Steam');
        const otherSources = sources.filter(s => s !== 'Steam');

        if (steamSource && otherSources.length > 0) {
            // If Steam exists and there are other sources, prompt for confirmation
            deleteConfirmMessage.textContent = `This game is owned on Steam and other platforms. Do you want to remove the Steam version or choose another?`;
            deleteSourceSelect.innerHTML = '';
            // Add Steam first
            deleteSourceSelect.add(new Option('Steam', 'Steam'));
            // Add other sources, excluding Steam
            otherSources.forEach(source => {
                deleteSourceSelect.add(new Option(source.replace('_', ' '), source));
            });
            deleteSourceSelect.style.display = 'block'; // Show dropdown
        } else if (sources.length > 1) {
            // If multiple sources but no Steam priority, let user choose
            deleteConfirmMessage.textContent = `This game is owned on multiple platforms. Which version do you want to remove?`;
            deleteSourceSelect.innerHTML = '';
            sources.forEach(source => {
                deleteSourceSelect.add(new Option(source.replace('_', ' '), source));
            });
            deleteSourceSelect.style.display = 'block'; // Show dropdown
        } else if (sources.length === 1) {
            // If only one source, confirm directly
            deleteConfirmMessage.textContent = `Are you sure you want to remove this game from your library? (Source: ${sources[0].replace('_', ' ')})`;
            deleteSourceSelect.style.display = 'none'; // Hide dropdown
        } else {
            // Should not happen if button is only shown for owned games, but as a fallback
            alert('No source found for this game. Cannot delete.');
            return;
        }
        deleteConfirmModal.style.display = 'block';
    }

    confirmDeleteButton.addEventListener('click', async () => {
        const { gameId, sources } = gameToDelete;
        let sourceToRemove = null;

        if (sources.length > 1) {
            sourceToRemove = deleteSourceSelect.value;
        } else if (sources.length === 1) {
            sourceToRemove = sources[0];
        }

        if (!sourceToRemove) {
            alert('Please select a source to remove.');
            return;
        }

        try {
            const response = await fetch('/api/manage/delete_game', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ discord_id: currentDiscordId, game_id: gameId, source: sourceToRemove }),
            });
            console.log('Delete API Response Status:', response.status);
            const result = await response.json();
            console.log('Delete API Response Body:', result);
            if (result.success) {
                showToast('Game removed successfully!');
                loadUserLibrary(currentDiscordId); // Reload library
                deleteConfirmModal.style.display = 'none';
            } else {
                showToast('Failed to remove game: ' + result.error, true);
            }
        } catch (error) {
            console.error('Error removing game:', error);
            showToast('An error occurred while removing the game.', true);
        }
    });

    cancelDeleteButton.addEventListener('click', () => {
        deleteConfirmModal.style.display = 'none';
    });

    deleteModalCloseButton.addEventListener('click', () => {
        deleteConfirmModal.style.display = 'none';
    });

    window.addEventListener('click', (event) => {
        if (event.target === deleteConfirmModal) {
            deleteConfirmModal.style.display = 'none';
        }
    });

    async function handleToggleInstalled(gameId) {
        try {
            const response = await fetch('/api/manage/toggle_installed', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ discord_id: currentDiscordId, game_id: gameId }),
            });
            const result = await response.json();
            if (result.success) {
                alert('Game installation status updated!');
                loadUserLibrary(currentDiscordId); // Reload library to reflect changes
            } else {
                alert('Failed to update installation status: ' + result.error);
            }
        } catch (error) {
            console.error('Error toggling installed status:', error);
            alert('An error occurred while updating installation status.');
        }
    }

    async function handleLikeGame(gameId, likeButton, dislikeButton) {
        try {
            const response = await fetch('/api/manage/like_game', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ discord_id: currentDiscordId, game_id: gameId }),
            });
            const result = await response.json();
            if (result.success) {
                likeButton.classList.toggle('active', result.liked);
                dislikeButton.classList.toggle('active', result.disliked);
            } else {
                alert('Failed to like game: ' + result.error);
            }
        } catch (error) {
            console.error('Error liking game:', error);
            alert('An error occurred while liking the game.');
        }
    }

    async function handleDislikeGame(gameId, dislikeButton, likeButton) {
        try {
            const response = await fetch('/api/manage/dislike_game', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ discord_id: currentDiscordId, game_id: gameId }),
            });
            const result = await response.json();
            if (result.success) {
                dislikeButton.classList.toggle('active', result.disliked);
                likeButton.classList.toggle('active', result.liked);
            } else {
                alert('Failed to dislike game: ' + result.error);
            }
        } catch (error) {
            console.error('Error disliking game:', error);
            alert('An error occurred while disliking the game.');
        }
    }

    // --- Start the application ---
    initialize();
});
