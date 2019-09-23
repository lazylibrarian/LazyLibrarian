
function initHeader() {
    //settings
    var header = $("#container header");
    var fadeSpeed = 100, fadeTo = 1.0, topDistance = 20;
    var topbarME = function () { $(header).fadeTo(fadeSpeed, 1); }, topbarML = function () { $(header).fadeTo(fadeSpeed, fadeTo); };
    var inside = false;
    //do
    $(window).scroll(function () {
        position = $(window).scrollTop();
        if (position > topDistance && !inside) {
            //add events
            topbarML();
            $(header).bind('mouseenter', topbarME);
            $(header).bind('mouseleave', topbarML);
            $("#toTop").fadeIn();
            inside = true;
        }
        else if (position < topDistance) {
            topbarME();
            $(header).unbind('mouseenter', topbarME);
            $(header).unbind('mouseleave', topbarML);
            $("#toTop").fadeOut();
            inside = false;
        }
    });

}

function showMsg(msg, loader, timeout, ms) {

    if ($(".msg").length == 0) // only allow one message to be displayed at a time
    {
        var feedback = $("#ajaxMsg");
        update = $("#updatebar");
        if (update.is(":visible")) {
            var height = update.height() + 35;
            feedback.css("bottom", height + "px");
        } else {
            feedback.removeAttr("style");
        }
        feedback.fadeIn();
        var message = $("<div class='msg'>" + msg + "</div>");
        if (loader) {
            var message = $("<div class='msg'><img src='images/loader_black.gif' alt='loading' class='loader' style='position: relative;top:10px;margin-top:-15px; margin-left:-10px;'/>" + msg + "</div>");
            feedback.css("padding", "14px 10px")
        }
        $(feedback).prepend(message);
        if (timeout) {
            setTimeout(function () {
                message.fadeOut(function () {
                    $(this).remove();
                    feedback.fadeOut();
                });
            }, ms);
        }
    }
}

function doAjaxCall(url, elem, reload, form) {
    // Set Message
    feedback = $("#ajaxMsg");
    update = $("#updatebar");
    if (update.is(":visible")) {
        var height = update.height() + 35;
        feedback.css("bottom", height + "px");
    } else {
        feedback.removeAttr("style");
    }

    feedback.fadeIn();
    // Get Form data
    var formID = "#" + url;
    if (form == true) {
        var dataString = $(formID).serialize();
    }
    // Loader Image
    var loader = $("<img src='interfaces/default/images/loader_black.gif' alt='loading' class='loader'/>");
    // Data Success Message
    var dataSucces = $(elem).data('success');
    if (typeof dataSucces === "undefined") {
        // Standard Message when variable is not set
        var dataSucces = "Success!";
    }
    // Data Errror Message
    var dataError = $(elem).data('error');
    if (typeof dataError === "undefined") {
        // Standard Message when variable is not set
        var dataError = "There was an error";
    }
    // Get Success & Error message from inline data, else use standard message
    var succesMsg = $("<div class='msg'><span class='ui-icon ui-icon-check'></span>" + dataSucces + "</div>");
    var errorMsg = $("<div class='msg'><span class='ui-icon ui-icon-alert'></span>" + dataError + "</div>");

    // Ajax Call
    $.ajax({
        url: url,
        data: dataString,
        beforeSend: function (jqXHR, settings) {
            // Start loader etc.
            feedback.prepend(loader);
        },
        error: function (jqXHR, textStatus, errorThrown) {
            feedback.addClass('error')
            feedback.prepend(errorMsg);
            setTimeout(function () {
                errorMsg.fadeOut(function () {
                    $(this).remove();
                    feedback.fadeOut(function () {
                        feedback.removeClass('error')
                    });
                })
            }, 2000);
        },
        success: function (data, jqXHR) {
            feedback.prepend(succesMsg);
            feedback.addClass('success')
            setTimeout(function (e) {
                succesMsg.fadeOut(function () {
                    $(this).remove();
                    feedback.fadeOut(function () {
                        feedback.removeClass('success');
                    });
                    if (reload == true) refreshSubmenu();
                    if (reload == "table") {
                        console.log('refresh'); refreshTable();
                    }
                    if (reload == "tabs") refreshTab();
                    if (form) {
                        // Change the option to 'choose...'
                        $(formID + " select").children('option[disabled=disabled]').attr('selected', 'selected');
                    }
                })
            }, 2000);
        },
        complete: function (jqXHR, textStatus) {
            // Remove loaders and stuff, ajax request is complete!
            loader.remove();
        }
    });
}

function checkForNotification() {
    
}

function init() {
    initHeader();
    setInterval(function () { checkForNotification(); }, 3000); // Check for notifications every 9 secconds
}

$(document).ready(function () {
    init();
});
