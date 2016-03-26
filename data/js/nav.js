$(document).ready(function() {
    // get document url
    var docURL = document.URL;

    // reset class of nav links
    $("#navbardiv a").removeClass("navactive");

    // pull our page
    var page = location.pathname.substring( location.pathname.lastIndexOf("/") + 1 );

    // add active class
    $("#navbardiv a:not(.navbarlogo)[href=\""+page+"\"]").addClass("navactive");
});
