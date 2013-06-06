function restartQA(e, message, title) {
    var self = this;

    var q = new Question('Are you sure you want to restart LazyLibrarian?', 'Restart', [{
        'text': 'Restart',
        'class': 'restart orange',
        'events': {
            'click': function(e){
                (e).preventDefault();
                self.restart(message, title);
                q.close.delay(100, q);
            }
        }
    }, {
        'text': 'Cancel',
        'cancel': true
    }]);
}

function restart(message, title) {
    window.location.href = "restart";
}

function shutdownQA(e) {
    var self = this;

    var q = new Question('Are you sure you want to shutdown LazyLibrarian?', 'Shutdown', [{
        'text': 'Shutdown',
        'class': 'shutdown red',
        'events': {
            'click': function(e){
                (e).preventDefault();
                self.shutdown();
                q.close.delay(100, q);
            }
        }
    }, {
        'text': 'Cancel',
        'cancel': true
    }]);
}

function shutdown() {
    window.location.href= "shutdown";
}