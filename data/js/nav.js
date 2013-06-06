$(document).ready(function() {
    // get document url
    var docURL = document.URL;
	
	// reset class of nav links
	var box = document.getElementById('home');
	box.setAttribute('class', 'authors');
	box = document.getElementById('books');
	box.setAttribute('class', 'books');
	box = document.getElementById('logs');
	box.setAttribute('class', 'logs');
	box = document.getElementById('config');
	box.setAttribute('class', 'config');

	// add active class
	if (docURL.indexOf("home") != -1) {
			box = document.getElementById('home');
			box.setAttribute('class', 'authorsActive');
	};
	if (docURL.indexOf("author") != -1) {
			box = document.getElementById('home');
			box.setAttribute('class', 'authorsActive');
	};
	if (docURL.indexOf("books") != -1) {
			box = document.getElementById('books');
			box.setAttribute('class', 'booksActive');
	};
	if (docURL.indexOf("logs") != -1) {
			box = document.getElementById('logs');
			box.setAttribute('class', 'logsActive');
	};
	if (docURL.indexOf("config") != -1) {
			box = document.getElementById('config');
			box.setAttribute('class', 'configActive');
	};
});