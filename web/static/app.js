document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    const gameGrid = document.getElementById('game-grid');
    const libraryTitle = document.getElementById('library-title');
    const userSwitcher = document.getElementById('user-switcher');
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
        loadUserLibrary(currentDiscordId);
    }

    function loadUsers() {
        fetch('/api/users')
            .then(res => res.json())
            .then(users => {
                users.sort((a, b) => a.username.localeCompare(b.username));
                userSwitcher.innerHTML = '';
                users.forEach(user => {
                    const option = new Option(user.username, user.discord_id);
                    if (user.discord_id === currentDiscordId) {
                        option.selected = true;
                        libraryTitle.textContent = `${user.username}'s Library`;
                    }
                    userSwitcher.add(option);
                });
            });
    }

    let isCurrentUserLibrary = false;

    function loadUserLibrary(discordId) {
        currentDiscordId = discordId;
        isCurrentUserLibrary = (currentDiscordId === viewerId);

        const selectedUser = Array.from(userSwitcher.options).find(opt => opt.value === discordId);
        if (selectedUser) libraryTitle.textContent = `${selectedUser.textContent}'s Library`;

        fetch(`/api/games/${discordId}`)
            .then(res => res.json())
            .then(games => {
                allGames = games.sort((a, b) => a.name.localeCompare(b.name));
                populateFilters(allGames);
                applyFilters();
            });
    }

    // --- Event Listeners for Filters ---
    userSwitcher.addEventListener('change', () => loadUserLibrary(userSwitcher.value));
    [nameFilterInput, platformFilter, playersFilter, gamepassFilter].forEach(el => el.addEventListener('input', applyFilters));

    // --- Filtering Logic ---
    function populateFilters(games) {
        const allSources = new Set();
        games.forEach(game => {
            game.sources.forEach(source => allSources.add(source));
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
        const gamepassChecked = gamepassFilter.checked;

        const filteredGames = allGames.filter(game => {
            const nameMatch = game.name.toLowerCase().includes(nameQuery);
            // Check if the game's sources include the selected platformQuery
            const platformMatch = !platformQuery || game.sources.includes(platformQuery);
            const playersMatch = !playersQuery || (game.max_players >= playersQuery);
            const gamepassMatch = !gamepassChecked || game.is_game_pass;
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
                                <button class="toggle-owned-button" data-game-id="${game.id}">
                                    ${game.sources.length > 0 ? 'Mark as Un-Owned' : 'Mark as Owned'}
                                </button>
                                <button class="toggle-installed-button" data-game-id="${game.id}" ${game.sources.length === 0 ? 'disabled' : ''}>
                                    ${game.is_installed ? 'Mark as Uninstalled' : 'Mark as Installed'}
                                </button>
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
                const toggleOwnedButton = cardContainer.querySelector('.toggle-owned-button');
                if (toggleOwnedButton) {
                    toggleOwnedButton.addEventListener('click', (event) => {
                        event.stopPropagation(); // Prevent card flip
                        handleToggleOwned(game.id);
                    });
                }

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
                });
        }
    }

    // --- New Game Management Functions ---
    async function handleToggleOwned(gameId) {
        try {
            const response = await fetch('/api/manage/toggle_owned', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ discord_id: currentDiscordId, game_id: gameId }),
            });
            const result = await response.json();
            if (result.success) {
                alert('Game ownership status updated!');
                loadUserLibrary(currentDiscordId); // Reload library to reflect changes
            } else {
                alert('Failed to update ownership status: ' + result.error);
            }
        } catch (error) {
            console.error('Error toggling ownership status:', error);
            alert('An error occurred while updating ownership status.');
        }
    }

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
